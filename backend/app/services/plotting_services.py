import matplotlib.pyplot as plt


# =========================================================
#                   TIME SLICE PLOTTER
# =========================================================

class TimeSlicePlotter:
    def __init__(self, time_slice_result: dict):
        """
        time_slice_result: output of run_time_slice_analysis

        Expected structure:
        {
            "Days of Week": {
                "Monday": {
                    "trades_count": int,
                    "win_rate_pct": float,
                    "avg_return_pct": float,
                    ...
                },
                ...
            },
            ...
        }
        """
        self.data = time_slice_result

    # ================= INTERNAL HELPERS ================= #

    def _validate_unit(self, unit_name: str):
        if unit_name not in self.data or not self.data[unit_name]:
            print(f"[PLOT] No data for {unit_name}")
            return False
        return True

    def _extract_metric(self, unit_data: dict, metric: str):
        labels = list(unit_data.keys())
        values = [unit_data[k].get(metric, 0) for k in labels]
        return labels, values

    # ================= CORE PLOTS ================= #

    def _plot_combined(self, unit_name: str):
        """
        Trade count bar with win-rate filled portion (existing behavior)
        """
        if not self._validate_unit(unit_name):
            return

        unit_data = self.data[unit_name]

        labels = list(unit_data.keys())
        trade_counts = [unit_data[k].get("trades_count", 0) for k in labels]
        win_rates = [unit_data[k].get("win_rate_pct", 0) for k in labels]

        x = range(len(labels))

        plt.figure(figsize=(10, 5))

        # Base bar: total trades
        plt.bar(
            x,
            trade_counts,
            color="#ffcccc",
            edgecolor="black",
            label="Total Trades"
        )

        # Filled portion: winning trades
        filled_height = [
            tc * wr / 100 for tc, wr in zip(trade_counts, win_rates)
        ]

        plt.bar(
            x,
            filled_height,
            color="#4CAF50",
            label="Winning Trades"
        )

        # Annotation
        max_tc = max(trade_counts) if trade_counts else 1
        for xi, tc, wr in zip(x, trade_counts, win_rates):
            plt.text(
                xi,
                tc + max_tc * 0.02,
                f"{tc} ({wr:.0f}%)",
                ha="center",
                va="bottom",
                fontsize=9
            )

        plt.xticks(x, labels, rotation=45)
        plt.ylabel("Number of Trades")
        plt.title(f"Time Slice Analysis – {unit_name}")
        plt.legend()
        plt.tight_layout()
        plt.show()

    def _plot_single_metric(self, unit_name: str, metric: str, ylabel: str, title_suffix: str):
        """
        Plot one metric ONLY (clean & interpretable)
        """
        if not self._validate_unit(unit_name):
            return

        unit_data = self.data[unit_name]
        labels, values = self._extract_metric(unit_data, metric)

        x = range(len(labels))

        plt.figure(figsize=(10, 5))
        bars = plt.bar(x, values, edgecolor="black")

        max_val = max(values) if values else 1

        for bar, val in zip(bars, values):
            plt.text(
                bar.get_x() + bar.get_width() / 2,
                val + max_val * 0.02,
                f"{val:.2f}",
                ha="center",
                va="bottom",
                fontsize=9
            )

        plt.xticks(x, labels, rotation=45)
        plt.ylabel(ylabel)
        plt.title(f"{title_suffix} – {unit_name}")
        plt.tight_layout()
        plt.show()

    # ================= PUBLIC API ================= #

    def plot(self):
        """Plot combined chart for all available time units"""
        for unit in self.data.keys():
            self._plot_combined(unit)

    # ----- Combined (existing behavior) -----

    def weeks(self):
        self._plot_combined("Week of Month")

    def days(self):
        self._plot_combined("Days of Week")

    def months(self):
        self._plot_combined("Month")

    def hours(self):
        self._plot_combined("Hour")

    def years(self):
        self._plot_combined("Year")

    # ----- NEW: Metric-wise plots -----

    def plot_trades(self, unit_name: str):
        self._plot_single_metric(
            unit_name,
            metric="trades_count",
            ylabel="Number of Trades",
            title_suffix="Trade Count"
        )

    def plot_win_rate(self, unit_name: str):
        self._plot_single_metric(
            unit_name,
            metric="win_rate_pct",
            ylabel="Win Rate (%)",
            title_suffix="Win Rate"
        )

    def plot_total_return(self, unit_name: str):
        self._plot_single_metric(
            unit_name,
            metric="total_return_pct",
            ylabel="Total Return (%)",
            title_suffix="Total Return"
        )



# =========================================================
#               BACKTEST STATS VISUALIZER
# =========================================================

class BacktestStatsVisualizer:
    def __init__(self, stats: dict):
        """
        stats: output from backtest_result["backtest_result"]
        """
        self.stats = stats

    def plot_table(self, highlight_keys=None):
        """
        Clean, readable stats table.
        - All floats rounded to 2 decimals
        - No misleading plots
        """
        highlight_keys = highlight_keys or [
            "Total Trades",
            "Win Rate [%]",
            "Total Return [%]",
            "Max Drawdown [%]",
            "Sharpe Ratio"
        ]

        keys = list(self.stats.keys())
        values = [
            round(v, 2) if isinstance(v, float) else v
            for v in self.stats.values()
        ]

        fig, ax = plt.subplots(figsize=(10, len(keys) * 0.35))
        ax.axis("off")

        table_data = [[k, v] for k, v in zip(keys, values)]

        table = ax.table(
            cellText=table_data,
            colLabels=["Metric", "Value"],
            cellLoc="center",
            loc="center",
            colColours=["#40466e", "#40466e"],
            colWidths=[0.6, 0.4]
        )

        for i, k in enumerate(keys):
            row_color = "#ffd700" if k in highlight_keys else "#f0f0f0"
            for j in range(2):
                table[(i + 1, j)].set_facecolor(row_color)
                table[(i + 1, j)].set_edgecolor("black")
                table[(i + 1, j)].set_fontsize(10)

        for j in range(2):
            table[(0, j)].set_text_props(weight="bold", color="white")
            table[(0, j)].set_fontsize(12)

        plt.title("Backtest Summary Statistics", fontsize=14, weight="bold")
        plt.tight_layout()
        plt.show()
