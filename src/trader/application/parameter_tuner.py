"""Parameter tuning service for dynamic strategy optimization.

Provides safe parameter validation, update, and application services
for trading strategies, with rollback capabilities.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from decimal import Decimal
from dataclasses import dataclass
from pydantic import BaseModel, Field, field_validator
from enum import Enum

from ..ai.strategy_params import StrategyParams, RiskLevel
from ..infrastructure.event_bus import EventBus, Event, EventType
from ..infrastructure.clock import IClock


class ParameterChangeType(str, Enum):
    """Type of parameter change."""
    RISK_LEVEL = "risk_level"
    POSITION_SIZE = "position_size"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    INDICATOR_PERIOD = "indicator_period"
    CUSTOM = "custom"


class ParameterValidationError(Exception):
    """Error when parameter validation fails."""
    pass


class ParameterChange(BaseModel):
    """Record of a parameter change."""
    timestamp: datetime = Field(description="Time of the change")
    change_type: ParameterChangeType = Field(description="Type of parameter change")
    parameter_name: str = Field(description="Name of the parameter")
    old_value: Any = Field(description="Previous value")
    new_value: Any = Field(description="New value")
    reason: str = Field(description="Reason for the change")
    source: str = Field(description="Source of the change (user, ai, etc.)")
    success: bool = Field(default=True, description="Whether the change was successful")


class ParameterConstraints(BaseModel):
    """Constraints for parameter validation."""
    min_value: Optional[Decimal] = Field(default=None, description="Minimum allowed value")
    max_value: Optional[Decimal] = Field(default=None, description="Maximum allowed value")
    allowed_values: Optional[List[Any]] = Field(default=None, description="List of allowed values")
    validator: Optional[Callable[[Any], bool]] = Field(default=None, description="Custom validator function")


class ParameterTuner:
    """Service for safe parameter tuning and management.

    Provides:
    - Parameter validation against constraints
    - Atomic parameter updates
    - Change history tracking
    - Rollback capabilities
    - Event notifications
    """

    def __init__(
        self,
        clock: IClock,
        event_bus: EventBus,
        initial_params: Optional[StrategyParams] = None,
    ):
        """Initialize parameter tuner.

        Args:
            clock: Clock for time management
            event_bus: Event bus for publishing events
            initial_params: Optional initial strategy parameters
        """
        self.clock = clock
        self.event_bus = event_bus
        self.current_params = initial_params or StrategyParams()
        self._default_params = self.current_params.model_copy()
        self._change_history: List[ParameterChange] = []
        self._constraints: Dict[str, ParameterConstraints] = {}

        self._setup_default_constraints()
        self._setup_event_listeners()

        self.logger = logging.getLogger(__name__)

    def _setup_default_constraints(self) -> None:
        """Set up default parameter constraints."""
        # Position size constraints: 1-100% of balance
        self._constraints["position_size_pct"] = ParameterConstraints(
            min_value=Decimal("0.01"),
            max_value=Decimal("1.0"),
        )

        # Stop loss constraints: 0.1-20%
        self._constraints["stop_loss_pct"] = ParameterConstraints(
            min_value=Decimal("0.001"),
            max_value=Decimal("0.2"),
        )

        # Take profit constraints: 0.1-50%
        self._constraints["take_profit_pct"] = ParameterConstraints(
            min_value=Decimal("0.001"),
            max_value=Decimal("0.5"),
        )

        # Risk level constraints: enum values
        self._constraints["risk_level"] = ParameterConstraints(
            allowed_values=[level.value for level in RiskLevel],
        )

        # Leverage constraints: 1-100x
        self._constraints["leverage"] = ParameterConstraints(
            min_value=Decimal("1"),
            max_value=Decimal("100"),
        )

        # SMA periods: 2-200
        self._constraints["sma_short_period"] = ParameterConstraints(
            min_value=Decimal("2"),
            max_value=Decimal("200"),
        )
        self._constraints["sma_long_period"] = ParameterConstraints(
            min_value=Decimal("2"),
            max_value=Decimal("200"),
        )

    def _setup_event_listeners(self) -> None:
        """Set up event bus listeners."""
        self.event_bus.subscribe(EventType.STRATEGY_PARAMS_UPDATED, self._on_params_update_request)

    def _on_params_update_request(self, event: Event) -> None:
        """Handle parameter update request events."""
        try:
            if "risk_level" in event.data:
                risk_level = RiskLevel(event.data["risk_level"])
                self.set_risk_level(risk_level, source="ai_reflexion")
        except Exception as e:
            self.logger.error(f"Failed to handle params update event: {e}")

    def validate_parameter(self, name: str, value: Any) -> bool:
        """Validate a parameter value against constraints.

        Args:
            name: Parameter name
            value: Parameter value to validate

        Returns:
            True if valid, raises ParameterValidationError otherwise

        Raises:
            ParameterValidationError: If validation fails
        """
        constraints = self._constraints.get(name)

        if constraints is None:
            # No constraints defined, assume valid
            return True

        # Check allowed values
        if constraints.allowed_values is not None:
            if value not in constraints.allowed_values:
                raise ParameterValidationError(
                    f"Parameter '{name}' value '{value}' not in allowed values: {constraints.allowed_values}"
                )

        # Check numeric constraints for Decimal/float/int values
        if constraints.min_value is not None or constraints.max_value is not None:
            try:
                num_value = Decimal(str(value))
                if constraints.min_value is not None and num_value < constraints.min_value:
                    raise ParameterValidationError(
                        f"Parameter '{name}' value {value} below minimum {constraints.min_value}"
                    )
                if constraints.max_value is not None and num_value > constraints.max_value:
                    raise ParameterValidationError(
                        f"Parameter '{name}' value {value} above maximum {constraints.max_value}"
                    )
            except (ValueError, TypeError):
                # Not a numeric value, skip numeric checks
                pass

        # Check custom validator
        if constraints.validator is not None:
            if not constraints.validator(value):
                raise ParameterValidationError(
                    f"Parameter '{name}' value '{value}' failed custom validation"
                )

        return True

    def update_parameter(
        self,
        name: str,
        value: Any,
        reason: str,
        source: str = "user",
    ) -> bool:
        """Update a single parameter.

        Args:
            name: Parameter name
            value: New parameter value
            reason: Reason for the change
            source: Source of the change (default: "user")

        Returns:
            True if update successful

        Raises:
            ParameterValidationError: If validation fails
        """
        # Validate first
        self.validate_parameter(name, value)

        # Get old value
        old_value = getattr(self.current_params, name, None)

        # Record the change attempt
        change = ParameterChange(
            timestamp=self.clock.now(),
            change_type=ParameterChangeType.CUSTOM,
            parameter_name=name,
            old_value=old_value,
            new_value=value,
            reason=reason,
            source=source,
            success=False,
        )

        try:
            # Update the parameter
            setattr(self.current_params, name, value)
            change.success = True

            self.logger.info(
                f"Parameter updated: {name} = {value} (was {old_value}) - {reason}"
            )

            # Publish event
            self.event_bus.publish(Event(
                type=EventType.STRATEGY_PARAMS_UPDATED,
                timestamp=self.clock.now(),
                data={
                    "parameter": name,
                    "old_value": old_value,
                    "new_value": value,
                    "reason": reason,
                },
            ))

            return True

        except Exception as e:
            self.logger.error(f"Failed to update parameter {name}: {e}")
            return False

        finally:
            self._change_history.append(change)

    def set_risk_level(
        self,
        risk_level: RiskLevel,
        reason: str,
        source: str = "user",
    ) -> bool:
        """Set risk level and adjust related parameters.

        Args:
            risk_level: Target risk level
            reason: Reason for the change
            source: Source of the change

        Returns:
            True if successful
        """
        # Get the preset parameters for this risk level
        preset_params = StrategyParams.from_risk_level(risk_level)

        # Record the risk level change
        change = ParameterChange(
            timestamp=self.clock.now(),
            change_type=ParameterChangeType.RISK_LEVEL,
            parameter_name="risk_level",
            old_value=self.current_params.risk_level.value if self.current_params.risk_level else None,
            new_value=risk_level.value,
            reason=reason,
            source=source,
            success=True,
        )

        try:
            # Update all parameters to match the risk level
            self.current_params = preset_params

            self._change_history.append(change)

            self.logger.info(f"Risk level set to {risk_level.value} - {reason}")

            # Publish event
            self.event_bus.publish(Event(
                type=EventType.STRATEGY_PARAMS_UPDATED,
                timestamp=self.clock.now(),
                data={
                    "risk_level": risk_level.value,
                    "reason": reason,
                },
            ))

            return True

        except Exception as e:
            self.logger.error(f"Failed to set risk level: {e}")
            change.success = False
            self._change_history.append(change)
            return False

    def batch_update(
        self,
        updates: Dict[str, Any],
        reason: str,
        source: str = "user",
    ) -> bool:
        """Update multiple parameters atomically.

        Args:
            updates: Dictionary of parameter name to new value
            reason: Reason for the changes
            source: Source of the changes

        Returns:
            True if all updates successful
        """
        # Validate all parameters first
        for name, value in updates.items():
            self.validate_parameter(name, value)

        # If all valid, perform updates
        success = True
        old_values = {}

        # Save old values
        for name in updates.keys():
            old_values[name] = getattr(self.current_params, name, None)

        # Apply updates
        for name, value in updates.items():
            try:
                setattr(self.current_params, name, value)
                # Record individual change
                self._change_history.append(ParameterChange(
                    timestamp=self.clock.now(),
                    change_type=ParameterChangeType.CUSTOM,
                    parameter_name=name,
                    old_value=old_values[name],
                    new_value=value,
                    reason=reason,
                    source=source,
                    success=True,
                ))
            except Exception as e:
                self.logger.error(f"Failed to update {name}: {e}")
                success = False

        if success:
            self.event_bus.publish(Event(
                type=EventType.STRATEGY_PARAMS_UPDATED,
                timestamp=self.clock.now(),
                data={"updates": updates, "reason": reason},
            ))

        return success

    def rollback(self, steps: int = 1) -> bool:
        """Rollback parameter changes.

        Args:
            steps: Number of changes to rollback (default: 1)

        Returns:
            True if rollback successful
        """
        if steps <= 0:
            raise ValueError("Steps must be positive")

        if len(self._change_history) < steps:
            self.logger.warning("Not enough history to rollback")
            return False

        # Get the changes to rollback
        changes_to_rollback = self._change_history[-steps:]

        # Apply in reverse order
        for change in reversed(changes_to_rollback):
            if change.success:
                try:
                    setattr(self.current_params, change.parameter_name, change.old_value)
                    self.logger.info(
                        f"Rolled back {change.parameter_name} to {change.old_value}"
                    )
                except Exception as e:
                    self.logger.error(f"Failed to rollback {change.parameter_name}: {e}")
                    return False

        # Remove from history
        self._change_history = self._change_history[:-steps]

        return True

    def reset_to_defaults(self) -> bool:
        """Reset all parameters to default values.

        Returns:
            True if successful
        """
        old_params = self.current_params
        self.current_params = self._default_params.model_copy()

        self.logger.info("Parameters reset to defaults")

        self._change_history.append(ParameterChange(
            timestamp=self.clock.now(),
            change_type=ParameterChangeType.CUSTOM,
            parameter_name="all",
            old_value=old_params.model_dump(),
            new_value=self._default_params.model_dump(),
            reason="Reset to defaults",
            source="system",
            success=True,
        ))

        self.event_bus.publish(Event(
            type=EventType.STRATEGY_PARAMS_UPDATED,
            timestamp=self.clock.now(),
            data={"action": "reset"},
        ))

        return True

    def get_current_params(self) -> StrategyParams:
        """Get current strategy parameters.

        Returns:
            Current StrategyParams
        """
        return self.current_params.model_copy()

    def get_change_history(self, limit: Optional[int] = None) -> List[ParameterChange]:
        """Get parameter change history.

        Args:
            limit: Optional maximum number of changes to return

        Returns:
            List of ParameterChange objects
        """
        history = self._change_history
        if limit is not None:
            history = history[-limit:]
        return history.copy()

    def set_constraint(self, name: str, constraints: ParameterConstraints) -> None:
        """Set or update constraints for a parameter.

        Args:
            name: Parameter name
            constraints: Constraints to apply
        """
        self._constraints[name] = constraints
