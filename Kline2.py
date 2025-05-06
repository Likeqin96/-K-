import os
import struct
import random
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import mplfinance as mpf
import pandas as pd

# ==================== 全局配置 ====================
FONT_PATH = 'C:/Windows/Fonts/msyh.ttc'          # 微软雅黑字体路径
BASE_STOCK_PATH = r'G:\tdx'                      # 通达信数据根目录
INITIAL_CAPITAL = 100000                         # 初始资金（元）
SIMULATION_DAYS = 120                            # 模拟交易天数
MA_PERIODS = [5, 10, 20, 60, 120, 250]           # 均线周期
MA_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c',    # 均线颜色
             '#d62728', '#9467bd', '#8c564b']

# ==================== 字体初始化 ====================
try:
    font_prop = font_manager.FontProperties(fname=FONT_PATH)
    plt.rcParams['font.sans-serif'] = [font_prop.get_name()]
    plt.rcParams['axes.unicode_minus'] = False
except Exception as e:
    print(f"字体加载失败: {str(e)}")
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False

# ==================== 图表样式配置 ====================
market_colors = mpf.make_marketcolors(
    up='r',         # 上涨K线红色
    down='g',       # 下跌K线绿色
    edge='inherit',
    wick='inherit',
    volume='inherit'
)

chart_style = mpf.make_mpf_style(
    marketcolors=market_colors,
    base_mpl_style='default',
    rc={
        'font.family': plt.rcParams['font.sans-serif'][0],
        'axes.titlesize': 12,
        'axes.labelsize': 10
    }
)

# ==================== 数据读取函数 ====================
def read_day_file(file_path):
    """读取通达信.day文件"""
    data = []
    try:
        with open(file_path, 'rb') as f:
            buffer = f.read()
            num_records = len(buffer) // 32
            
            for i in range(num_records):
                raw_data = struct.unpack('IIIIIfII', buffer[i*32:(i+1)*32])
                date = datetime.strptime(f"{raw_data[0]}", "%Y%m%d")
                data.append([
                    date,
                    raw_data[1]/100,   # 开盘价
                    raw_data[2]/100,   # 最高价
                    raw_data[3]/100,   # 最低价
                    raw_data[4]/100,   # 收盘价
                    raw_data[6]        # 成交量
                ])
        
        df = pd.DataFrame(data, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df.set_index('Date', inplace=True)
        return df
    except Exception as e:
        raise ValueError(f"文件读取失败: {str(e)}")

# ==================== 交易模拟器类 ====================
class TradingSimulator:
    def __init__(self, master):
        self.master = master
        self.master.title("股票交易模拟系统")
        self.master.geometry("1400x900")
        
        # 初始化状态变量
        self.current_data = pd.DataFrame()
        self.current_index = 64       # 显示65根K线
        self.cash = INITIAL_CAPITAL
        self.position = 0
        self.trade_log = []
        self.equity_curve = [INITIAL_CAPITAL]
        self.buy_signals = pd.DataFrame(columns=['Price'])
        self.sell_signals = pd.DataFrame(columns=['Price'])
        
        # 股票数据路径
        self.stock_pool = {
            "沪市": os.path.join(BASE_STOCK_PATH, "vipdoc", "sh", "lday"),
            "深市": os.path.join(BASE_STOCK_PATH, "vipdoc", "sz", "lday"),
            "创业板": os.path.join(BASE_STOCK_PATH, "vipdoc", "sz", "lday")
        }
        
        # 初始化界面
        self._init_ui()
        self._init_chart_components()  # 初始化图表组件

    def _init_ui(self):
        """初始化用户界面"""
        # 控制面板
        control_frame = ttk.Frame(self.master)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 市场选择
        ttk.Label(control_frame, text="选择市场:").pack(side=tk.LEFT)
        self.market_var = tk.StringVar()
        market_combo = ttk.Combobox(control_frame, textvariable=self.market_var, 
                                   values=list(self.stock_pool.keys()), width=8)
        market_combo.pack(side=tk.LEFT, padx=5)
        
        # 操作按钮
        ttk.Button(control_frame, text="开始模拟", command=self._start_simulation).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="买入", command=lambda: self._execute_trade("buy")).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="卖出", command=lambda: self._execute_trade("sell")).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="观望", command=lambda: self._execute_trade("hold")).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="结束统计", command=self._show_summary).pack(side=tk.RIGHT)
        
        # 信息显示
        self.info_label = ttk.Label(self.master, text="就绪", font=(plt.rcParams['font.sans-serif'][0], 10))
        self.info_label.pack(pady=5)
        
        # 图表区域
        self.chart_frame = ttk.Frame(self.master)
        self.chart_frame.pack(fill=tk.BOTH, expand=True)

    def _init_chart_components(self):
        """初始化图表组件（解决闪烁问题的关键）"""
        # 创建持久的Figure和Axes
        self.fig = mpf.figure(style=chart_style, figsize=(13, 8))
        self.ax_price = self.fig.add_subplot(2, 1, 1)
        self.ax_volume = self.fig.add_subplot(2, 1, 2, sharex=self.ax_price)
        
        # 创建Canvas并固定布局
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.fig.set_tight_layout(True)  # 优化布局
        self._draw_placeholder()  # 初始绘制空图表

    def _draw_placeholder(self):
        """绘制初始占位图表"""
        self.ax_price.clear()
        self.ax_volume.clear()
        self.ax_price.text(0.5, 0.5, '等待数据加载...', 
                          ha='center', va='center', fontsize=16)
        self.canvas.draw()

    def _start_simulation(self):
        """开始新的模拟"""
        try:
            market = self.market_var.get()
            if not market:
                raise ValueError("请先选择市场类型")
                
            # 检查数据路径
            data_path = self.stock_pool.get(market)
            if not os.path.exists(data_path):
                raise FileNotFoundError(f"{market}数据路径不存在")
                
            # 加载数据
            valid_files = [f for f in os.listdir(data_path) 
                          if f.endswith('.day') and f.startswith(('sh', 'sz'))]
            if not valid_files:
                raise ValueError("该市场没有有效数据文件")
                
            stock_file = random.choice(valid_files)
            self.current_data = read_day_file(os.path.join(data_path, stock_file))
            
            # 验证数据量
            required_days = SIMULATION_DAYS + 65
            if len(self.current_data) < required_days:
                raise ValueError(f"需要至少 {required_days} 天历史数据")
            
            # 初始化状态
            start_idx = random.randint(0, len(self.current_data) - required_days)
            self.current_data = self.current_data.iloc[start_idx:start_idx+required_days]
            self._reset_trading_state()
            self._update_chart()
            self._update_info()
            
        except Exception as e:
            messagebox.showerror("初始化失败", str(e))
            self._draw_placeholder()

    def _reset_trading_state(self):
        """重置交易状态"""
        self.current_index = 64
        self.cash = INITIAL_CAPITAL
        self.position = 0
        self.trade_log = []
        self.equity_curve = [INITIAL_CAPITAL]
        self.buy_signals = pd.DataFrame(columns=['Price'])
        self.sell_signals = pd.DataFrame(columns=['Price'])

    def _execute_trade(self, action):
        """执行交易操作（优化后的无闪烁版本）"""
        if self.current_index >= len(self.current_data) - 1:
            messagebox.showinfo("提示", "已到达数据末尾")
            return
            
        try:
            current_bar = self.current_data.iloc[self.current_index]
            price = current_bar.Close
            date = current_bar.name
            
            if action == "buy":
                if self.position > 0:
                    raise ValueError("请先卖出当前持仓")
                max_shares = self.cash // price
                if max_shares < 1:
                    raise ValueError("可用资金不足")
                
                self.position = max_shares
                self.cash -= max_shares * price
                self.buy_signals.loc[date] = {'Price': price}
                
            elif action == "sell":
                if self.position == 0:
                    raise ValueError("没有可卖出的持仓")
                self.cash += self.position * price
                self.position = 0
                self.sell_signals.loc[date] = {'Price': price}
            
            # 更新交易记录
            self.trade_log.append({
                'date': date,
                'action': action,
                'price': price,
                'shares': self.position if action == 'buy' else 0,
                'cash': self.cash
            })
            
            # 更新资产曲线
            total_value = self.cash + self.position * price
            self.equity_curve.append(total_value)
            self.current_index += 1
            
            self._update_chart()
            self._update_info()
            
        except Exception as e:
            messagebox.showwarning("交易失败", str(e))

    def _update_chart(self):
        """更新图表（无闪烁实现）"""
        # 清除旧内容
        self.ax_price.clear()
        self.ax_volume.clear()
        
        # 准备数据（显示最近65根K线）
        plot_data = self.current_data.iloc[self.current_index-64:self.current_index+1]
        
        # 生成移动平均线
        add_plots = []
        for period, color in zip(MA_PERIODS, MA_COLORS):
            if len(plot_data) > period:
                ma = plot_data.Close.rolling(period).mean()
                add_plots.append(mpf.make_addplot(ma, color=color, ax=self.ax_price))
        
        # 生成买卖信号
        if not self.buy_signals.empty:
            buy_plot = mpf.make_addplot(
                self.buy_signals['Price'].reindex(plot_data.index),
                type='scatter', 
                markersize=100, 
                marker='^', 
                color='red',
                ax=self.ax_price
            )
            add_plots.append(buy_plot)
            
        if not self.sell_signals.empty:
            sell_plot = mpf.make_addplot(
                self.sell_signals['Price'].reindex(plot_data.index),
                type='scatter', 
                markersize=100, 
                marker='v', 
                color='green',
                ax=self.ax_price
            )
            add_plots.append(sell_plot)
        
        # 绘制主图表（复用现有Axes）
        mpf.plot(
            plot_data,
            type='candle',
            style=chart_style,
            volume=self.ax_volume,
            addplot=add_plots,
            ax=self.ax_price,
            update_width_config=dict(
                candle_linewidth=1.0,
                candle_width=0.8
            ),
            returnfig=True
        )
        
        # 优化重绘过程
        self.ax_price.legend(loc='upper left')
        self.fig.tight_layout()
        self.canvas.draw_idle()  # 关键：使用增量更新

    def _update_info(self):
        """更新信息显示"""
        current = self.current_data.iloc[self.current_index]
        total = self.cash + self.position * current.Close
        info = [
            f"日期: {current.name.strftime('%Y-%m-%d')}",
            f"开盘: {current.Open:.2f} 收盘: {current.Close:.2f}",
            f"持仓: {self.position}股 现金: ¥{self.cash:.2f}",
            f"总资产: ¥{total:.2f}"
        ]
        self.info_label.config(text=" | ".join(info))

    def _show_summary(self):
        """显示统计结果"""
        if not self.trade_log:
            messagebox.showinfo("统计", "暂无交易记录")
            return
            
        # 计算胜率
        win_trades = 0
        total_trades = 0
        last_buy_price = None
        
        for trade in self.trade_log:
            if trade['action'] == 'buy':
                last_buy_price = trade['price']
            elif trade['action'] == 'sell' and last_buy_price:
                total_trades += 1
                if trade['price'] > last_buy_price:
                    win_trades += 1
                last_buy_price = None
                
        win_rate = win_trades / total_trades if total_trades > 0 else 0
        
        # 计算最大回撤
        peak = self.equity_curve[0]
        max_drawdown = 0
        for value in self.equity_curve:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                
        # 显示结果
        result = [
            f"初始资金: ¥{INITIAL_CAPITAL:.2f}",
            f"最终资产: ¥{self.equity_curve[-1]:.2f}",
            f"收益率: {(self.equity_curve[-1]/INITIAL_CAPITAL-1):.2%}",
            f"胜率: {win_rate:.2%}",
            f"最大回撤: {max_drawdown:.2%}",
            f"交易次数: {total_trades}"
        ]
        messagebox.showinfo("模拟统计", "\n".join(result))

if __name__ == "__main__":
    root = tk.Tk()
    try:
        # 设置全局字体
        root.option_add("*Font", (plt.rcParams['font.sans-serif'][0], 10))
    except Exception as e:
        print(f"界面字体设置失败: {str(e)}")
    app = TradingSimulator(root)
    root.mainloop()