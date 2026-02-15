"""Reflexion Loop for AI-powered trading strategy optimization.

Implements the observe-reason-act-execute loop for continuous
strategy improvement based on market conditions.
"""
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from decimal import Decimal
from pydantic import BaseModel, Field
from enum import Enum

from .llm_client import LLMClient, LLMMessage, LLMFunctionCall
from .tools import get_tool_definitions, ToolExecutor
from .strategy_params import StrategyParams, RiskLevel
from ..infrastructure.clock import IClock
from ..infrastructure.event_bus import EventBus, Event, EventType
from ..infrastructure.data_repository import DataRepository, BarData


class ReflexionState(str, Enum):
    """State of the reflexion loop."""
    OBSERVING = "observing"
    REASONING = "reasoning"
    ACTING = "acting"
    EXECUTING = "executing"
    IDLE = "idle"


class Observation(BaseModel):
    """Market observation data."""
    timestamp: datetime = Field(description="Timestamp of the observation")
    symbol: str = Field(description="Trading pair symbol")
    current_price: Decimal = Field(description="Current price")
    price_change_24h: Decimal = Field(description="24-hour price change percentage")
    volume_24h: Decimal = Field(description="24-hour trading volume")
    technical_indicators: Dict[str, Any] = Field(default_factory=dict, description="Technical indicators")
    market_regime: str = Field(default="unknown", description="Market regime classification")
    recent_trades: List[Dict] = Field(default_factory=list, description="Recent trade history")
    position_state: Optional[Dict] = Field(default=None, description="Current position state")


class Reasoning(BaseModel):
    """AI reasoning output."""
    market_analysis: str = Field(description="Analysis of current market conditions")
    risk_assessment: str = Field(description="Risk assessment")
    recommended_action: str = Field(description="Recommended action")
    confidence: float = Field(description="Confidence level (0-1)")
    reasoning: str = Field(description="Detailed reasoning")


class Action(BaseModel):
    """Action to be executed."""
    action_type: str = Field(description="Type of action")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    description: str = Field(description="Human-readable description")


class ReflexionLoop:
    """Reflexion Loop for continuous strategy optimization.

    Implements the observe-reason-act-execute cycle:
    1. Observe: Collect market data and current state
    2. Reason: Analyze using LLM and decide on actions
    3. Act: Determine specific actions to take
    4. Execute: Apply actions to the trading system
    """

    def __init__(
        self,
        llm_client: LLMClient,
        clock: IClock,
        event_bus: EventBus,
        data_repository: Optional[DataRepository] = None,
        interval_hours: int = 4,
        symbol: str = "BTC/USDT",
    ):
        """Initialize the reflexion loop.

        Args:
            llm_client: LLM client for AI reasoning
            clock: Clock for time management
            event_bus: Event bus for communication
            data_repository: Optional data repository
            interval_hours: How often to run the loop (default: 4 hours)
            symbol: Trading pair symbol to monitor
        """
        self.llm_client = llm_client
        self.clock = clock
        self.event_bus = event_bus
        self.data_repository = data_repository
        self.interval_hours = interval_hours
        self.symbol = symbol

        self.state = ReflexionState.IDLE
        self.last_run: Optional[datetime] = None
        self.observation_history: List[Observation] = []
        self.action_history: List[Action] = []

        self.tool_executor = ToolExecutor()
        self._setup_event_listeners()

        self.logger = logging.getLogger(__name__)

    def _setup_event_listeners(self) -> None:
        """Set up event bus listeners."""
        self.event_bus.subscribe(EventType.BAR, self._on_market_event)
        self.event_bus.subscribe(EventType.POSITION_OPENED, self._on_position_event)
        self.event_bus.subscribe(EventType.POSITION_CLOSED, self._on_position_event)

    def _on_market_event(self, event: Event) -> None:
        """Handle market data events."""
        # Check if it's time to run the loop
        if self._should_run():
            self.run_full_cycle()

    def _on_position_event(self, event: Event) -> None:
        """Handle position events."""
        self.logger.info(f"Position event: {event.type}")

    def _should_run(self) -> bool:
        """Check if the reflexion loop should run now."""
        now = self.clock.now()
        
        if self.last_run is None:
            return True
        
        time_since_last = now - self.last_run
        return time_since_last >= timedelta(hours=self.interval_hours)

    def observe(self) -> Observation:
        """Step 1: Observe - Collect market data and state.

        Returns:
            Observation with current market state
        """
        self.state = ReflexionState.OBSERVING
        self.logger.info("Starting observation phase")

        now = self.clock.now()

        # Get market data
        current_price = Decimal("0")
        price_change_24h = Decimal("0")
        volume_24h = Decimal("0")
        technical_indicators = {}

        if self.data_repository:
            bars = self.data_repository.get_bars(self.symbol, limit=100)
            if bars:
                current_price = bars[-1].close
                if len(bars) >= 96:  # ~24 hours of 15min bars
                    price_24h_ago = bars[-96].close
                    price_change_24h = (current_price - price_24h_ago) / price_24h_ago * Decimal("100")
                volume_24h = sum(bar.volume for bar in bars[-96:]) if len(bars) >= 96 else Decimal("0")

        # Get position state
        position_state = None
        # This would be populated from the broker in a real implementation

        observation = Observation(
            timestamp=now,
            symbol=self.symbol,
            current_price=current_price,
            price_change_24h=price_change_24h,
            volume_24h=volume_24h,
            technical_indicators=technical_indicators,
            market_regime=self._classify_market_regime(price_change_24h, volume_24h),
            position_state=position_state,
        )

        self.observation_history.append(observation)
        self.logger.info(f"Observation complete: {observation.market_regime}")

        return observation

    def _classify_market_regime(self, price_change: Decimal, volume: Decimal) -> str:
        """Classify the current market regime."""
        if abs(price_change) > Decimal("5"):
            return "volatile"
        elif price_change > Decimal("2"):
            return "bullish"
        elif price_change < Decimal("-2"):
            return "bearish"
        else:
            return "ranging"

    def reason(self, observation: Observation) -> Reasoning:
        """Step 2: Reason - Analyze and make decisions using LLM.

        Args:
            observation: Current market observation

        Returns:
            Reasoning with AI analysis
        """
        self.state = ReflexionState.REASONING
        self.logger.info("Starting reasoning phase")

        # Build the prompt
        system_prompt = """You are an expert cryptocurrency trading strategist. Your role is to:
1. Analyze market conditions objectively
2. Assess risks carefully
3. Recommend parameter adjustments (NOT direct trades)
4. Always prioritize capital preservation

You can only recommend adjusting strategy parameters through the available tools.
Never suggest direct trades. Your recommendations should be conservative."""

        user_message = self._build_reasoning_prompt(observation)

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_message),
        ]

        # Get function definitions
        functions = get_tool_definitions()

        try:
            response = self.llm_client.chat(
                messages=messages,
                functions=functions,
                temperature=0.7,
            )

            reasoning = self._parse_reasoning_response(response, observation)
            self.logger.info(f"Reasoning complete: {reasoning.recommended_action}")

            return reasoning

        except Exception as e:
            self.logger.error(f"Reasoning failed: {e}")
            # Fallback to conservative reasoning
            return Reasoning(
                market_analysis="Market analysis unavailable due to technical issues",
                risk_assessment="High uncertainty, recommend conservative approach",
                recommended_action="maintain",
                confidence=0.5,
                reasoning="Fallback to conservative strategy due to analysis failure",
            )

    def _build_reasoning_prompt(self, observation: Observation) -> str:
        """Build the prompt for the LLM reasoning."""
        return f"""
Current Market State (as of {observation.timestamp}):
- Symbol: {observation.symbol}
- Current Price: ${observation.current_price:,.2f}
- 24h Change: {observation.price_change_24h:+.2f}%
- 24h Volume: {observation.volume_24h:,.0f}
- Market Regime: {observation.market_regime}

Recent Observations:
{self._format_recent_observations()}

Please analyze the market conditions and recommend strategy parameter adjustments.
Use the provided tools to make specific recommendations.
"""

    def _format_recent_observations(self, limit: int = 5) -> str:
        """Format recent observations for the prompt."""
        recent = self.observation_history[-limit:]
        lines = []
        for obs in recent:
            lines.append(f"- {obs.timestamp}: {obs.market_regime}, ${obs.current_price:,.2f}")
        return "\n".join(lines) if lines else "No previous observations"

    def _parse_reasoning_response(
        self,
        response,
        observation: Observation,
    ) -> Reasoning:
        """Parse the LLM response into Reasoning."""
        # If there's a function call, that's our action
        if response.function_calls:
            # For now, extract reasoning from content if available
            content = response.content or "Analysis complete"
            return Reasoning(
                market_analysis=content,
                risk_assessment="Based on current market conditions",
                recommended_action="adjust_parameters",
                confidence=0.8,
                reasoning=content,
            )
        else:
            content = response.content or "No specific recommendation"
            return Reasoning(
                market_analysis=content,
                risk_assessment="Conservative approach recommended",
                recommended_action="maintain",
                confidence=0.6,
                reasoning=content,
            )

    def act(self, reasoning: Reasoning, observation: Observation) -> List[Action]:
        """Step 3: Act - Determine specific actions to take.

        Args:
            reasoning: AI reasoning output
            observation: Current market observation

        Returns:
            List of Action objects to execute
        """
        self.state = ReflexionState.ACTING
        self.logger.info("Starting action phase")

        actions: List[Action] = []

        # Based on reasoning, create appropriate actions
        if reasoning.recommended_action == "adjust_parameters":
            # Adjust risk level based on market regime
            if observation.market_regime == "volatile":
                actions.append(Action(
                    action_type="adjust_risk_level",
                    parameters={"risk_level": "CONSERVATIVE"},
                    description="Switch to conservative mode due to volatility",
                ))
            elif observation.market_regime == "bullish":
                actions.append(Action(
                    action_type="adjust_risk_level",
                    parameters={"risk_level": "MEDIUM"},
                    description="Use medium risk in bullish market",
                ))
            elif observation.market_regime == "bearish":
                actions.append(Action(
                    action_type="adjust_risk_level",
                    parameters={"risk_level": "CONSERVATIVE"},
                    description="Be conservative in bearish market",
                ))

        self.action_history.extend(actions)
        self.logger.info(f"Action phase complete: {len(actions)} actions")

        return actions

    def execute(self, actions: List[Action]) -> bool:
        """Step 4: Execute - Apply actions to the system.

        Args:
            actions: List of actions to execute

        Returns:
            True if all actions executed successfully
        """
        self.state = ReflexionState.EXECUTING
        self.logger.info(f"Starting execution phase: {len(actions)} actions")

        success = True

        for action in actions:
            try:
                self._execute_single_action(action)
                self.logger.info(f"Executed: {action.description}")
            except Exception as e:
                self.logger.error(f"Failed to execute {action.action_type}: {e}")
                success = False

        self.state = ReflexionState.IDLE
        self.last_run = self.clock.now()

        return success

    def _execute_single_action(self, action: Action) -> None:
        """Execute a single action."""
        if action.action_type == "adjust_risk_level":
            risk_level = RiskLevel(action.parameters["risk_level"])
            # Publish event for parameter tuner
            self.event_bus.publish(Event(
                type=EventType.STRATEGY_PARAMS_UPDATED,
                timestamp=self.clock.now(),
                data={"risk_level": risk_level.value},
            ))

    def run_full_cycle(self) -> bool:
        """Run a complete observe-reason-act-execute cycle.

        Returns:
            True if cycle completed successfully
        """
        self.logger.info("Starting full reflexion cycle")

        try:
            observation = self.observe()
            reasoning = self.reason(observation)
            actions = self.act(reasoning, observation)
            success = self.execute(actions)

            if success:
                self.logger.info("Reflexion cycle completed successfully")
            else:
                self.logger.warning("Reflexion cycle completed with some failures")

            return success

        except Exception as e:
            self.logger.error(f"Reflexion cycle failed: {e}")
            self.state = ReflexionState.IDLE
            return False
