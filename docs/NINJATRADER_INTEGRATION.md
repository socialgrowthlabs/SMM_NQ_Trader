# NinjaTrader Integration with SMM NQ Trader

This document describes the integration between NinjaTrader and the SMM NQ Trader system for external signal processing and multi-account synchronization.

## Overview

The integration allows NinjaTrader to send entry and exit signals to the SMM trading engine, which then manages multi-account synchronization and execution. The system supports:

- **Entry Signals**: Long and short entry signals from NinjaTrader charts
- **Exit Signals**: Position exit signals for profit taking or stop losses
- **Filter Controls**: Long on/off and short on/off filters
- **Multi-Account Sync**: Ensures all accounts execute signals simultaneously
- **Real-time Processing**: Signals are processed immediately upon receipt

## Components

### 1. NinjaTrader Indicator (`SMMSignalIndicator.cs`)

Located in `/ninjatrader/SMMSignalIndicator.cs`, this C# indicator:

- **Generates Signals**: Creates entry/exit signals based on price movement
- **Plots Signals**: Visual indicators on the chart for signal confirmation
- **Sends to API**: HTTP POST requests to the SMM web server
- **Configurable**: Adjustable parameters for signal generation

#### Key Features:
- **Signal Types**: Entry (BUY/SELL) and Exit signals
- **Filter Controls**: Long on/off and short on/off switches
- **Cooldown Period**: Minimum time between signals (default: 30 seconds)
- **Price Movement**: Minimum price change to trigger signal (default: 0.25)
- **API Integration**: REST API communication with SMM system

#### Configuration Parameters:
```csharp
ApiBaseUrl = "http://localhost:8000"        // SMM web server URL
ApiPassword = ""                            // Authentication password
SignalCooldownSeconds = 30                  // Minimum time between signals
MinPriceMove = 0.25                         // Minimum price change
EnableSignalLogging = true                  // Console logging
LongSignalsEnabled = true                   // Enable long signals
ShortSignalsEnabled = true                  // Enable short signals
```

### 2. Web API Endpoints

The SMM web server provides REST API endpoints for signal processing:

#### Signal Reception
- **POST** `/api/signals/external` - Receive external signals
- **GET** `/api/signals/external` - Get recent external signals

#### Filter Controls
- **POST** `/api/control/filters` - Update signal filters
- **GET** `/api/control/filters` - Get current filter status
- **POST** `/api/control/filters/long/enable` - Enable long signals
- **POST** `/api/control/filters/long/disable` - Disable long signals
- **POST** `/api/control/filters/short/enable` - Enable short signals
- **POST** `/api/control/filters/short/disable` - Disable short signals

#### Synchronization
- **GET** `/api/control/sync/stats` - Get sync statistics
- **GET** `/api/control/sync/positions` - Get account positions

### 3. External Signal Processor

Located in `/core/external_signal_processor.py`, this component:

- **Processes Signals**: Handles incoming external signals
- **Account Sync**: Manages multi-account synchronization
- **Filter Management**: Applies long/short signal filters
- **Execution Integration**: Integrates with SMM execution engine

#### Key Features:
- **Real-time Processing**: Processes signals as they arrive
- **Account Synchronization**: Ensures all accounts execute simultaneously
- **Filter Controls**: Long/short signal filtering
- **Rate Limiting**: Prevents excessive signal processing
- **Error Handling**: Robust error handling and logging

### 4. Account Synchronization Manager

Located in `/core/account_sync_manager.py`, this component:

- **Account Management**: Tracks account states and synchronization
- **Sync Groups**: Groups accounts for synchronized trading
- **Status Tracking**: Monitors account synchronization status
- **Error Recovery**: Handles synchronization failures

#### Key Features:
- **Multi-Account Support**: Manages multiple trading accounts
- **Sync Groups**: Group accounts for coordinated execution
- **Status Monitoring**: Real-time synchronization status
- **Error Recovery**: Automatic retry and error handling

## Signal Flow

1. **NinjaTrader** generates signal based on chart analysis
2. **HTTP POST** to SMM web server `/api/signals/external`
3. **Web Server** validates and stores signal
4. **Signal Processor** processes signal asynchronously
5. **Account Sync Manager** synchronizes across accounts
6. **Execution Engine** submits orders to all accounts
7. **Order Management** tracks and manages positions

## Setup Instructions

### 1. NinjaTrader Setup

1. **Copy Indicator**: Copy `SMMSignalIndicator.cs` to NinjaTrader indicators folder
2. **Compile**: Compile the indicator in NinjaTrader
3. **Add to Chart**: Add indicator to your NQ chart
4. **Configure**: Set API URL and password in indicator properties
5. **Enable**: Enable long/short signals as needed

### 2. SMM System Setup

1. **Start Web Server**: Ensure SMM web server is running
2. **Start Signal Processor**: Run `scripts/start_external_signal_processor.py`
3. **Configure Accounts**: Set up trading accounts in `accounts/accounts.yaml`
4. **Test Connection**: Verify NinjaTrader can connect to SMM API

### 3. Configuration

#### NinjaTrader Indicator Properties:
```
API Base URL: http://localhost:8000
API Password: [your_password]
Signal Cooldown: 30 seconds
Min Price Move: 0.25
Long Signals: Enabled
Short Signals: Enabled
```

#### SMM Configuration:
```yaml
# config/config.yaml
strategy:
  external_signals:
    enabled: true
    cooldown_seconds: 5
    max_signals_per_minute: 10
  filters:
    long_signals_enabled: true
    short_signals_enabled: true
```

## API Usage Examples

### Send Entry Signal
```bash
curl -X POST "http://localhost:8000/api/signals/external" \
  -H "Content-Type: application/json" \
  -H "X-Dash-Pass: your_password" \
  -d '{
    "timestamp": 1640995200,
    "symbol": "NQZ5",
    "side": "BUY",
    "signal_type": "ENTRY",
    "price": 15000.0,
    "reason": "Long entry signal from NinjaTrader",
    "source": "ninjatrader",
    "confidence_score": 0.8,
    "exchange": "CME"
  }'
```

### Enable Long Signals
```bash
curl -X POST "http://localhost:8000/api/control/filters/long/enable" \
  -H "X-Dash-Pass: your_password"
```

### Get Sync Statistics
```bash
curl -X GET "http://localhost:8000/api/control/sync/stats" \
  -H "X-Dash-Pass: your_password"
```

## Monitoring and Troubleshooting

### Signal Processing Status
- Check web dashboard at `http://localhost:8000/ui`
- Monitor signal logs in `storage/state/external_signals.json`
- Review processing statistics via API

### Common Issues

1. **Connection Failed**: Check API URL and password
2. **Signals Not Processing**: Verify signal processor is running
3. **Account Sync Issues**: Check account configuration and status
4. **Filter Problems**: Verify filter settings via API

### Log Files
- **External Signals**: `storage/state/external_signals.json`
- **Processed Signals**: `storage/state/processed_external_signals.json`
- **Sync State**: `storage/state/account_sync_state.json`
- **Signal Filters**: `storage/state/signal_filters.json`

## Security Considerations

- **API Authentication**: Use strong passwords for API access
- **Network Security**: Consider VPN or firewall protection
- **Signal Validation**: All signals are validated before processing
- **Rate Limiting**: Built-in rate limiting prevents abuse

## Performance Optimization

- **Signal Cooldown**: Adjust cooldown period based on strategy needs
- **Account Limits**: Limit number of accounts for better performance
- **Network Latency**: Consider local network for low latency
- **Resource Usage**: Monitor CPU and memory usage

## Support and Maintenance

- **Regular Updates**: Keep NinjaTrader and SMM system updated
- **Backup Configuration**: Backup configuration files regularly
- **Monitor Performance**: Track signal processing performance
- **Error Logging**: Review error logs for troubleshooting

## Conclusion

The NinjaTrader integration provides a robust solution for external signal processing with multi-account synchronization. The system is designed for reliability, performance, and ease of use, enabling traders to leverage NinjaTrader's charting capabilities with SMM's execution engine.

For additional support or questions, refer to the main SMM documentation or contact the development team.
