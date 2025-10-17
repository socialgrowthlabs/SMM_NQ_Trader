using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;

namespace NinjaTrader.NinjaScript.Indicators
{
    /// <summary>
    /// SMM Signal Indicator for SMM NQ Trader Integration
    /// Sends entry/exit signals to the SMM trading engine via REST API
    /// </summary>
    public class SMMSignalIndicator : Indicator
    {
        #region Variables
        private HttpClient httpClient;
        private string apiBaseUrl = "http://localhost:8000"; // Default SMM web server URL
        private string apiPassword = ""; // Set via properties
        
        // Signal state tracking
        private bool lastLongSignal = false;
        private bool lastShortSignal = false;
        private double lastSignalPrice = 0;
        private DateTime lastSignalTime = DateTime.MinValue;
        
        // Filter controls
        private bool longSignalsEnabled = true;
        private bool shortSignalsEnabled = true;
        
        // Signal plots
        private Series<double> longEntryPlot;
        private Series<double> shortEntryPlot;
        private Series<double> longExitPlot;
        private Series<double> shortExitPlot;
        
        // Configuration
        private int signalCooldownSeconds = 30; // Minimum time between signals
        private double minPriceMove = 0.25; // Minimum price move to trigger signal
        private bool enableSignalLogging = true;
        
        // Signal definition parameters
        private int emaFastPeriod = 8; // Fast EMA period
        private int emaSlowPeriod = 21; // Slow EMA period
        private int emaTrendPeriod = 55; // Trend EMA period
        private double volumeThreshold = 1.5; // Volume multiplier threshold
        private bool useEmaCrossover = true; // Use EMA crossover signals
        private bool usePriceBreakout = false; // Use price breakout signals
        private bool useVolumeConfirmation = true; // Require volume confirmation
        private bool useTrendFilter = true; // Use trend filter (EMA55)
        
        // Technical indicators
        private Series<double> emaFast;
        private Series<double> emaSlow;
        private Series<double> emaTrend;
        private Series<double> volumeMA;
        
        #endregion

        #region OnStateChange
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "SMM Signal Indicator for SMM NQ Trader Integration";
                Name = "SMM Signal Indicator";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = true;
                DrawOnPricePanel = true;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;
                IsSuspendedWhileInactive = true;
                
                // Add plots for signals
                AddPlot(Brushes.Green, "Long Entry");
                AddPlot(Brushes.Red, "Short Entry");
                AddPlot(Brushes.DarkGreen, "Long Exit");
                AddPlot(Brushes.DarkRed, "Short Exit");
                
                // Set plot styles
                Plots[0].PlotStyle = PlotStyle.Dot;
                Plots[1].PlotStyle = PlotStyle.Dot;
                Plots[2].PlotStyle = PlotStyle.Dot;
                Plots[3].PlotStyle = PlotStyle.Dot;
                
                // Initialize series
                longEntryPlot = new Series<double>(this);
                shortEntryPlot = new Series<double>(this);
                longExitPlot = new Series<double>(this);
                shortExitPlot = new Series<double>(this);
                
                // Initialize technical indicators
                emaFast = new Series<double>(this);
                emaSlow = new Series<double>(this);
                emaTrend = new Series<double>(this);
                volumeMA = new Series<double>(this);
                
                // Default values
                ApiBaseUrl = "http://localhost:8000";
                ApiPassword = "";
                SignalCooldownSeconds = 30;
                MinPriceMove = 0.25;
                EnableSignalLogging = true;
                LongSignalsEnabled = true;
                ShortSignalsEnabled = true;
                
                // Signal definition defaults
                EmaFastPeriod = 8;
                EmaSlowPeriod = 21;
                EmaTrendPeriod = 55;
                VolumeThreshold = 1.5;
                UseEmaCrossover = true;
                UsePriceBreakout = false;
                UseVolumeConfirmation = true;
                UseTrendFilter = true;
            }
            else if (State == State.Configure)
            {
                // Initialize HTTP client
                httpClient = new HttpClient();
                httpClient.Timeout = TimeSpan.FromSeconds(10);
            }
            else if (State == State.Terminated)
            {
                httpClient?.Dispose();
            }
        }
        #endregion

        #region OnBarUpdate
        protected override void OnBarUpdate()
        {
            if (CurrentBar < 1) return;
            
            // Calculate technical indicators
            CalculateIndicators();
            
            // Update series
            longEntryPlot[0] = double.NaN;
            shortEntryPlot[0] = double.NaN;
            longExitPlot[0] = double.NaN;
            shortExitPlot[0] = double.NaN;
            
            // Check for signal conditions
            CheckForSignals();
        }
        #endregion

        #region Signal Detection Logic
        private void CalculateIndicators()
        {
            try
            {
                // Calculate EMAs
                if (CurrentBar >= emaFastPeriod)
                    emaFast[0] = EMA(emaFastPeriod)[0];
                
                if (CurrentBar >= emaSlowPeriod)
                    emaSlow[0] = EMA(emaSlowPeriod)[0];
                
                if (CurrentBar >= emaTrendPeriod)
                    emaTrend[0] = EMA(emaTrendPeriod)[0];
                
                // Calculate volume moving average
                if (CurrentBar >= 20)
                    volumeMA[0] = SMA(Volume, 20)[0];
            }
            catch (Exception ex)
            {
                if (enableSignalLogging)
                    Print($"Error calculating indicators: {ex.Message}");
            }
        }
        
        private void CheckForSignals()
        {
            try
            {
                double currentPrice = Close[0];
                double previousPrice = Close[1];
                
                // Check cooldown period
                if (DateTime.Now.Subtract(lastSignalTime).TotalSeconds < signalCooldownSeconds)
                    return;
                
                // Check if we have enough data
                if (CurrentBar < Math.Max(emaTrendPeriod, 20))
                    return;
                
                bool isLongSignal = false;
                bool isShortSignal = false;
                string signalReason = "";
                
                // EMA Crossover Signals
                if (useEmaCrossover)
                {
                    if (emaFast[0] > emaSlow[0] && emaFast[1] <= emaSlow[1])
                    {
                        isLongSignal = true;
                        signalReason = "EMA Crossover Bullish";
                    }
                    else if (emaFast[0] < emaSlow[0] && emaFast[1] >= emaSlow[1])
                    {
                        isShortSignal = true;
                        signalReason = "EMA Crossover Bearish";
                    }
                }
                
                // Price Breakout Signals
                if (usePriceBreakout && !isLongSignal && !isShortSignal)
                {
                    double priceChange = Math.Abs(currentPrice - previousPrice);
                    if (priceChange >= minPriceMove)
                    {
                        if (currentPrice > previousPrice)
                        {
                            isLongSignal = true;
                            signalReason = "Price Breakout Bullish";
                        }
                        else
                        {
                            isShortSignal = true;
                            signalReason = "Price Breakout Bearish";
                        }
                    }
                }
                
                // Apply trend filter
                if (useTrendFilter)
                {
                    if (isLongSignal && currentPrice < emaTrend[0])
                    {
                        isLongSignal = false;
                        signalReason = "Trend Filter Blocked Long";
                    }
                    if (isShortSignal && currentPrice > emaTrend[0])
                    {
                        isShortSignal = false;
                        signalReason = "Trend Filter Blocked Short";
                    }
                }
                
                // Apply volume confirmation
                if (useVolumeConfirmation && (isLongSignal || isShortSignal))
                {
                    double currentVolume = Volume[0];
                    double avgVolume = volumeMA[0];
                    
                    if (avgVolume > 0 && currentVolume < (avgVolume * volumeThreshold))
                    {
                        isLongSignal = false;
                        isShortSignal = false;
                        signalReason = "Volume Confirmation Failed";
                    }
                }
                
                // Apply filter controls
                if (isLongSignal && !longSignalsEnabled) 
                {
                    isLongSignal = false;
                    signalReason = "Long Signals Disabled";
                }
                if (isShortSignal && !shortSignalsEnabled) 
                {
                    isShortSignal = false;
                    signalReason = "Short Signals Disabled";
                }
                
                // Generate signals
                if (isLongSignal && !lastLongSignal)
                {
                    GenerateLongEntrySignal(currentPrice, signalReason);
                }
                else if (isShortSignal && !lastShortSignal)
                {
                    GenerateShortEntrySignal(currentPrice, signalReason);
                }
                
                // Check for exit signals (opposite direction)
                if (lastLongSignal && isShortSignal)
                {
                    GenerateLongExitSignal(currentPrice, "Long Exit Signal");
                }
                else if (lastShortSignal && isLongSignal)
                {
                    GenerateShortExitSignal(currentPrice, "Short Exit Signal");
                }
                
                // Update state
                lastLongSignal = isLongSignal;
                lastShortSignal = isShortSignal;
                lastSignalPrice = currentPrice;
                lastSignalTime = DateTime.Now;
            }
            catch (Exception ex)
            {
                if (enableSignalLogging)
                    Print($"Error in CheckForSignals: {ex.Message}");
            }
        }
        
        private void GenerateLongEntrySignal(double price, string reason)
        {
            try
            {
                longEntryPlot[0] = price;
                SendSignalToSMM("BUY", "ENTRY", price, reason);
                
                if (enableSignalLogging)
                    Print($"Long Entry Signal: {price} at {DateTime.Now:HH:mm:ss} - {reason}");
            }
            catch (Exception ex)
            {
                if (enableSignalLogging)
                    Print($"Error generating long entry signal: {ex.Message}");
            }
        }
        
        private void GenerateShortEntrySignal(double price, string reason)
        {
            try
            {
                shortEntryPlot[0] = price;
                SendSignalToSMM("SELL", "ENTRY", price, reason);
                
                if (enableSignalLogging)
                    Print($"Short Entry Signal: {price} at {DateTime.Now:HH:mm:ss} - {reason}");
            }
            catch (Exception ex)
            {
                if (enableSignalLogging)
                    Print($"Error generating short entry signal: {ex.Message}");
            }
        }
        
        private void GenerateLongExitSignal(double price, string reason)
        {
            try
            {
                longExitPlot[0] = price;
                SendSignalToSMM("SELL", "EXIT", price, reason);
                
                if (enableSignalLogging)
                    Print($"Long Exit Signal: {price} at {DateTime.Now:HH:mm:ss} - {reason}");
            }
            catch (Exception ex)
            {
                if (enableSignalLogging)
                    Print($"Error generating long exit signal: {ex.Message}");
            }
        }
        
        private void GenerateShortExitSignal(double price, string reason)
        {
            try
            {
                shortExitPlot[0] = price;
                SendSignalToSMM("BUY", "EXIT", price, reason);
                
                if (enableSignalLogging)
                    Print($"Short Exit Signal: {price} at {DateTime.Now:HH:mm:ss} - {reason}");
            }
            catch (Exception ex)
            {
                if (enableSignalLogging)
                    Print($"Error generating short exit signal: {ex.Message}");
            }
        }
        #endregion

        #region API Communication
        private async void SendSignalToSMM(string side, string signalType, double price, string reason)
        {
            try
            {
                var signalData = new
                {
                    timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
                    symbol = Instrument.MasterInstrument.Name,
                    side = side,
                    signal_type = signalType,
                    price = price,
                    reason = reason,
                    source = "ninjatrader",
                    confidence_score = 0.8, // Default confidence for external signals
                    atr_value = 0.0, // Will be calculated by SMM system
                    exchange = "CME"
                };
                
                string json = SerializeToJson(signalData);
                var content = new StringContent(json, Encoding.UTF8, "application/json");
                
                // Add password header if configured
                if (!string.IsNullOrEmpty(apiPassword))
                {
                    content.Headers.Add("X-Dash-Pass", apiPassword);
                }
                
                string url = $"{apiBaseUrl}/api/signals/external";
                var response = await httpClient.PostAsync(url, content);
                
                if (response.IsSuccessStatusCode)
                {
                    if (enableSignalLogging)
                        Print($"Signal sent successfully: {side} {signalType} at {price}");
                }
                else
                {
                    if (enableSignalLogging)
                        Print($"Failed to send signal: {response.StatusCode} - {response.ReasonPhrase}");
                }
            }
            catch (Exception ex)
            {
                if (enableSignalLogging)
                    Print($"Error sending signal to SMM: {ex.Message}");
            }
        }
        #endregion

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "API Base URL", Description = "Base URL for SMM web server", Order = 1, GroupName = "SMM Configuration")]
        public string ApiBaseUrl
        {
            get { return apiBaseUrl; }
            set { apiBaseUrl = value; }
        }
        
        [NinjaScriptProperty]
        [Display(Name = "API Password", Description = "Password for SMM web server authentication", Order = 2, GroupName = "SMM Configuration")]
        public string ApiPassword
        {
            get { return apiPassword; }
            set { apiPassword = value; }
        }
        
        [NinjaScriptProperty]
        [Range(1, 300)]
        [Display(Name = "Signal Cooldown (seconds)", Description = "Minimum time between signals", Order = 3, GroupName = "Signal Configuration")]
        public int SignalCooldownSeconds
        {
            get { return signalCooldownSeconds; }
            set { signalCooldownSeconds = Math.Max(1, value); }
        }
        
        [NinjaScriptProperty]
        [Range(0.25, 10.0)]
        [Display(Name = "Min Price Move", Description = "Minimum price change to trigger signal", Order = 4, GroupName = "Signal Configuration")]
        public double MinPriceMove
        {
            get { return minPriceMove; }
            set { minPriceMove = Math.Max(0.25, value); }
        }
        
        [NinjaScriptProperty]
        [Display(Name = "Enable Signal Logging", Description = "Enable console logging of signals", Order = 5, GroupName = "Signal Configuration")]
        public bool EnableSignalLogging
        {
            get { return enableSignalLogging; }
            set { enableSignalLogging = value; }
        }
        
        [NinjaScriptProperty]
        [Display(Name = "Long Signals Enabled", Description = "Enable long entry/exit signals", Order = 6, GroupName = "Signal Filters")]
        public bool LongSignalsEnabled
        {
            get { return longSignalsEnabled; }
            set { longSignalsEnabled = value; }
        }
        
        [NinjaScriptProperty]
        [Display(Name = "Short Signals Enabled", Description = "Enable short entry/exit signals", Order = 7, GroupName = "Signal Filters")]
        public bool ShortSignalsEnabled
        {
            get { return shortSignalsEnabled; }
            set { shortSignalsEnabled = value; }
        }
        
        [NinjaScriptProperty]
        [Range(5, 50)]
        [Display(Name = "EMA Fast Period", Description = "Fast EMA period for crossover signals", Order = 8, GroupName = "Signal Definition")]
        public int EmaFastPeriod
        {
            get { return emaFastPeriod; }
            set { emaFastPeriod = Math.Max(5, Math.Min(50, value)); }
        }
        
        [NinjaScriptProperty]
        [Range(10, 100)]
        [Display(Name = "EMA Slow Period", Description = "Slow EMA period for crossover signals", Order = 9, GroupName = "Signal Definition")]
        public int EmaSlowPeriod
        {
            get { return emaSlowPeriod; }
            set { emaSlowPeriod = Math.Max(10, Math.Min(100, value)); }
        }
        
        [NinjaScriptProperty]
        [Range(20, 200)]
        [Display(Name = "EMA Trend Period", Description = "Trend EMA period for trend filtering", Order = 10, GroupName = "Signal Definition")]
        public int EmaTrendPeriod
        {
            get { return emaTrendPeriod; }
            set { emaTrendPeriod = Math.Max(20, Math.Min(200, value)); }
        }
        
        [NinjaScriptProperty]
        [Range(1.0, 5.0)]
        [Display(Name = "Volume Threshold", Description = "Volume multiplier threshold for confirmation", Order = 11, GroupName = "Signal Definition")]
        public double VolumeThreshold
        {
            get { return volumeThreshold; }
            set { volumeThreshold = Math.Max(1.0, Math.Min(5.0, value)); }
        }
        
        [NinjaScriptProperty]
        [Display(Name = "Use EMA Crossover", Description = "Enable EMA crossover signals", Order = 12, GroupName = "Signal Definition")]
        public bool UseEmaCrossover
        {
            get { return useEmaCrossover; }
            set { useEmaCrossover = value; }
        }
        
        [NinjaScriptProperty]
        [Display(Name = "Use Price Breakout", Description = "Enable price breakout signals", Order = 13, GroupName = "Signal Definition")]
        public bool UsePriceBreakout
        {
            get { return usePriceBreakout; }
            set { usePriceBreakout = value; }
        }
        
        [NinjaScriptProperty]
        [Display(Name = "Use Volume Confirmation", Description = "Require volume confirmation for signals", Order = 14, GroupName = "Signal Definition")]
        public bool UseVolumeConfirmation
        {
            get { return useVolumeConfirmation; }
            set { useVolumeConfirmation = value; }
        }
        
        [NinjaScriptProperty]
        [Display(Name = "Use Trend Filter", Description = "Use EMA trend filter to block counter-trend signals", Order = 15, GroupName = "Signal Definition")]
        public bool UseTrendFilter
        {
            get { return useTrendFilter; }
            set { useTrendFilter = value; }
        }
        #endregion

        #region NinjaScript Generated Code
        // This region contains code that is automatically generated by NinjaTrader
        // Do not modify this region
        #endregion
        
        #region Helper Methods
        private string SerializeToJson(object obj)
        {
            try
            {
                var sb = new StringBuilder();
                sb.Append("{");
                
                var properties = obj.GetType().GetProperties();
                for (int i = 0; i < properties.Length; i++)
                {
                    var prop = properties[i];
                    var value = prop.GetValue(obj);
                    
                    if (i > 0) sb.Append(",");
                    sb.Append($"\"{prop.Name}\":");
                    
                    if (value is string str)
                        sb.Append($"\"{str}\"");
                    else if (value is double dbl)
                        sb.Append(dbl.ToString("F2"));
                    else if (value is float flt)
                        sb.Append(flt.ToString("F2"));
                    else if (value is int intVal)
                        sb.Append(intVal.ToString());
                    else if (value is bool boolVal)
                        sb.Append(boolVal.ToString().ToLower());
                    else
                        sb.Append($"\"{value}\"");
                }
                
                sb.Append("}");
                return sb.ToString();
            }
            catch (Exception ex)
            {
                if (enableSignalLogging)
                    Print($"Error serializing to JSON: {ex.Message}");
                return "{}";
            }
        }
        #endregion
    }
}
