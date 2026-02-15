"""Event bus implementation for publish-subscribe pattern.

Provides thread-safe event handling for the trading system.
"""
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable, Dict, List


class EventType(StrEnum):
    """Event types used in the trading system."""
    BAR = "bar"                    # K线事件
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    FUNDING_RATE_APPLIED = "funding_rate_applied"
    ERROR = "error"


@dataclass
class Event:
    """Event data structure."""
    type: EventType
    timestamp: datetime
    data: Dict[str, Any]
    source: str = "system"


class EventBus:
    """Event bus - publish-subscribe pattern with thread safety."""
    
    def __init__(self):
        """Initialize event bus."""
        self._subscribers: Dict[EventType, List[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Subscribe to an event type.
        
        Args:
            event_type: Type of event to subscribe to
            handler: Callback function to handle the event
        """
        with self._lock:
            self._subscribers[event_type].append(handler)
    
    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Unsubscribe from an event type.
        
        Args:
            event_type: Type of event to unsubscribe from
            handler: Callback function to remove
        """
        with self._lock:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)
    
    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers.
        
        Args:
            event: Event to publish
        """
        # Get handlers copy to avoid modification during iteration
        handlers = self._subscribers[event.type].copy()
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                # Publish error event
                self.publish(Event(
                    type=EventType.ERROR,
                    timestamp=event.timestamp,
                    data={"error": str(e), "original_event": event.type.value}
                ))
    
    def clear(self) -> None:
        """Clear all subscribers."""
        with self._lock:
            self._subscribers.clear()
