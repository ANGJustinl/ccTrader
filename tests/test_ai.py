"""Unit tests for the AI integration layer.

Tests tool definitions, strategy parameters, and AI agent framework.
"""
from decimal import Decimal
from datetime import datetime, timedelta
import pytest

from src.trader.ai import (
    AIAgent,
    StrategyParams,
    RiskLevel,
    ALL_TOOLS,
    ToolDefinition,
    ToolParameter,
    get_market_state_tool,
    adjust_strategy_params_tool,
    get_position_tool
)
from src.trader.application.strategies import AIEnhancedStrategy
from src.trader.application.backtest_engine import BacktestEngine
from src.trader.infrastructure.data_repository import BarData, FundingRateData


def generate_sample_test_data() -> tuple[list[BarData], list[FundingRateData]]:
    """生成测试用的简单数据"""
    bars = []
    funding_rates = []
    
    start_time = datetime(2024, 1, 1, tzinfo=datetime.now().astimezone().tzinfo)
    base_price = Decimal("50000")
    
    for i in range(100):
        trend = Decimal(str(i * 50))
        volatility = Decimal(str((i % 6) * 30))
        
        open_price = base_price + trend + volatility
        close_price = open_price + Decimal(str((i % 3 - 1) * 60))
        high_price = max(open_price, close_price) + Decimal("80")
        low_price = min(open_price, close_price) - Decimal("80")
        
        bar = BarData(
            symbol="BTC/USDT",
            timestamp=start_time + timedelta(minutes=15 * i),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=Decimal("100")
        )
        bars.append(bar)
    
    return bars, funding_rates


def test_ai_enhanced_strategy_initialization():
    """测试 AI 增强策略初始化"""
    strategy = AIEnhancedStrategy(fast_period=5, slow_period=10)
    assert strategy.fast_period == 5
    assert strategy.slow_period == 10
    assert strategy.ai_agent is not None
    assert strategy.current_params is not None


def test_ai_parameter_adjustment():
    """测试 AI 参数调整"""
    agent = AIAgent()
    initial_level = agent.strategy_params.risk_level
    
    agent.update_strategy_params(
        risk_level=RiskLevel.AGGRESSIVE,
        reasoning="测试"
    )
    
    assert agent.strategy_params.risk_level == RiskLevel.AGGRESSIVE


def test_ai_backtest_integration():
    """测试 AI 回测完整集成"""
    engine = BacktestEngine(initial_balance=Decimal("10000"))
    
    # 生成测试数据
    bars, _ = generate_sample_test_data()
    engine.load_data(bars)
    
    strategy = AIEnhancedStrategy()
    strategy.attach_backtest_engine(engine)
    
    engine.set_strategy(strategy.on_bar)
    results = engine.run("BTC/USDT")
    
    assert results is not None
    assert "final_balance" in results


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_risk_level_values(self):
        """Test RiskLevel enum has correct values."""
        assert RiskLevel.CONSERVATIVE == "conservative"
        assert RiskLevel.MODERATE == "moderate"
        assert RiskLevel.AGGRESSIVE == "aggressive"

    def test_risk_level_str_enum(self):
        """Test RiskLevel is a string enum."""
        assert isinstance(RiskLevel.CONSERVATIVE, str)
        assert isinstance(RiskLevel.MODERATE, str)
        assert isinstance(RiskLevel.AGGRESSIVE, str)


class TestToolParameter:
    """Tests for ToolParameter dataclass."""

    def test_tool_parameter_creation(self):
        """Test ToolParameter can be created."""
        param = ToolParameter(
            name="symbol",
            type="string",
            description="Trading pair, e.g., BTC/USDT",
            required=True
        )
        assert param.name == "symbol"
        assert param.type == "string"
        assert param.required is True

    def test_tool_parameter_with_enum(self):
        """Test ToolParameter with enum values."""
        param = ToolParameter(
            name="risk_level",
            type="string",
            description="Risk level",
            required=True,
            enum=["conservative", "moderate", "aggressive"]
        )
        assert param.enum == ["conservative", "moderate", "aggressive"]


class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""

    def test_tool_definition_creation(self):
        """Test ToolDefinition can be created."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters=[
                ToolParameter(name="param1", type="string", description="Param 1")
            ]
        )
        assert tool.name == "test_tool"
        assert len(tool.parameters) == 1

    def test_tool_to_openai_format(self):
        """Test ToolDefinition converts to OpenAI format correctly."""
        tool = ToolDefinition(
            name="get_market_state",
            description="Get market state",
            parameters=[
                ToolParameter(
                    name="symbol",
                    type="string",
                    description="Trading pair",
                    required=True
                )
            ]
        )
        openai_format = tool.to_openai_format()
        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "get_market_state"
        assert "symbol" in openai_format["function"]["parameters"]["properties"]


class TestAllTools:
    """Tests for ALL_TOOLS collection."""

    def test_all_tools_contains_expected_tools(self):
        """Test ALL_TOOLS contains the expected tools."""
        tool_names = [tool.name for tool in ALL_TOOLS]
        assert "get_market_state" in tool_names
        assert "adjust_strategy_params" in tool_names
        assert "get_position" in tool_names

    def test_get_market_state_tool_structure(self):
        """Test get_market_state_tool has correct structure."""
        assert get_market_state_tool.name == "get_market_state"
        param_names = [p.name for p in get_market_state_tool.parameters]
        assert "symbol" in param_names
        assert "indicators" in param_names

    def test_adjust_strategy_params_tool_structure(self):
        """Test adjust_strategy_params_tool has correct structure."""
        assert adjust_strategy_params_tool.name == "adjust_strategy_params"
        param_names = [p.name for p in adjust_strategy_params_tool.parameters]
        assert "strategy_id" in param_names
        assert "risk_level" in param_names
        assert "reasoning" in param_names

    def test_get_position_tool_structure(self):
        """Test get_position_tool has correct structure."""
        assert get_position_tool.name == "get_position"
        param_names = [p.name for p in get_position_tool.parameters]
        assert "symbol" in param_names


class TestStrategyParams:
    """Tests for StrategyParams model."""

    def test_default_params(self):
        """Test default strategy parameters."""
        params = StrategyParams.default()
        assert params.strategy_id == "default"
        assert params.risk_level == RiskLevel.MODERATE
        assert params.max_position_size == Decimal("0.1")
        assert params.leverage == 1

    def test_conservative_params(self):
        """Test conservative risk level parameters."""
        params = StrategyParams.from_risk_level(RiskLevel.CONSERVATIVE)
        assert params.risk_level == RiskLevel.CONSERVATIVE
        assert params.max_position_size == Decimal("0.05")
        assert params.leverage == 1

    def test_aggressive_params(self):
        """Test aggressive risk level parameters."""
        params = StrategyParams.from_risk_level(RiskLevel.AGGRESSIVE)
        assert params.risk_level == RiskLevel.AGGRESSIVE
        assert params.max_position_size == Decimal("0.2")
        assert params.leverage == 5

    def test_moderate_params(self):
        """Test moderate risk level parameters (default)."""
        params = StrategyParams.from_risk_level(RiskLevel.MODERATE)
        assert params.risk_level == RiskLevel.MODERATE
        assert params.max_position_size == Decimal("0.1")
        assert params.leverage == 1


class TestAIAgent:
    """Tests for AIAgent class."""

    def test_agent_creation(self):
        """Test AIAgent can be created."""
        agent = AIAgent(name="Test Agent")
        assert agent.name == "Test Agent"
        assert agent.strategy_params is not None

    def test_agent_with_custom_params(self):
        """Test AIAgent with custom strategy parameters."""
        custom_params = StrategyParams.from_risk_level(RiskLevel.AGGRESSIVE)
        agent = AIAgent(strategy_params=custom_params)
        assert agent.strategy_params.risk_level == RiskLevel.AGGRESSIVE

    def test_get_tool_definitions(self):
        """Test agent returns tool definitions in OpenAI format."""
        agent = AIAgent()
        tool_defs = agent.get_tool_definitions()
        assert len(tool_defs) > 0
        assert all("type" in td for td in tool_defs)
        assert all("function" in td for td in tool_defs)

    def test_get_market_state(self):
        """Test get_market_state tool."""
        agent = AIAgent()
        state = agent.get_market_state(symbol="BTC/USDT")
        assert state["symbol"] == "BTC/USDT"
        assert "timestamp" in state
        assert "indicators" in state

    def test_get_position_without_symbol(self):
        """Test get_position tool without symbol."""
        agent = AIAgent()
        position_info = agent.get_position()
        assert "has_position" in position_info
        assert "positions" in position_info

    def test_get_position_with_symbol(self):
        """Test get_position tool with specific symbol."""
        agent = AIAgent()
        position_info = agent.get_position(symbol="BTC/USDT")
        assert "has_position" in position_info
        assert "positions" in position_info

    def test_update_strategy_params(self):
        """Test update_strategy_params tool."""
        agent = AIAgent()
        initial_risk = agent.strategy_params.risk_level
        new_params = agent.update_strategy_params(
            risk_level=RiskLevel.AGGRESSIVE,
            reasoning="Testing aggressive strategy"
        )
        assert new_params.risk_level == RiskLevel.AGGRESSIVE
        assert agent.strategy_params.risk_level == RiskLevel.AGGRESSIVE

    def test_update_strategy_params_with_stop_loss(self):
        """Test update_strategy_params with custom stop loss."""
        agent = AIAgent()
        new_params = agent.update_strategy_params(
            risk_level=RiskLevel.MODERATE,
            stop_loss_pct=0.08,
            reasoning="Custom stop loss"
        )
        assert new_params.stop_loss_pct == Decimal("0.08")

    def test_execute_tool_call_get_market_state(self):
        """Test execute_tool_call for get_market_state."""
        agent = AIAgent()
        result = agent.execute_tool_call(
            tool_name="get_market_state",
            arguments={"symbol": "ETH/USDT"}
        )
        assert result["symbol"] == "ETH/USDT"

    def test_execute_tool_call_adjust_strategy_params(self):
        """Test execute_tool_call for adjust_strategy_params."""
        agent = AIAgent()
        result = agent.execute_tool_call(
            tool_name="adjust_strategy_params",
            arguments={
                "strategy_id": "test_strategy",
                "risk_level": "conservative",
                "reasoning": "Testing tool call"
            }
        )
        assert result["success"] is True
        assert result["params"].risk_level == RiskLevel.CONSERVATIVE

    def test_execute_tool_call_get_position(self):
        """Test execute_tool_call for get_position."""
        agent = AIAgent()
        result = agent.execute_tool_call(
            tool_name="get_position",
            arguments={"symbol": "BTC/USDT"}
        )
        assert "has_position" in result

    def test_execute_unknown_tool(self):
        """Test execute_tool_call with unknown tool returns error."""
        agent = AIAgent()
        result = agent.execute_tool_call(
            tool_name="unknown_tool",
            arguments={}
        )
        assert "error" in result

    def test_params_updated_callback(self):
        """Test on_params_updated callback is triggered."""
        callback_called = False
        callback_params = None

        def on_updated(params):
            nonlocal callback_called, callback_params
            callback_called = True
            callback_params = params

        agent = AIAgent()
        agent.on_params_updated = on_updated
        
        agent.update_strategy_params(
            risk_level=RiskLevel.AGGRESSIVE,
            reasoning="Callback test"
        )
        
        assert callback_called is True
        assert callback_params is not None
        assert callback_params.risk_level == RiskLevel.AGGRESSIVE
