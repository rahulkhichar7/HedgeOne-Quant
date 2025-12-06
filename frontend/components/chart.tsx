import { AreaData, AreaSeries, CandlestickData, CandlestickSeries, createChart, IChartApi, LineData, LineSeries, Time, WhitespaceData } from 'lightweight-charts'
import { useEffect, useRef, useState } from 'react'

export interface ChartData {
    label: string,
    color: string,
    type: "LineSeries" | "CandlesticksSeries" | "AreaSeries",
    data: (LineData<Time> | WhitespaceData<Time> | AreaData<Time> | CandlestickData<Time>)[],
    other: object       // not used
}

function typeOfSeries(type: string) {
    switch (type) {
        case "LineSeries":
            return LineSeries
        case "AreaSeries":
            return AreaSeries
        case "CandlesticksSeries":
            return CandlestickSeries
        default:
            throw Error("Invalid series type given")
    }
}

export function Chart({ data }: { data: ChartData[] }) {
    const containerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<IChartApi>(null)

    useEffect(() => {

        chartRef.current = createChart(containerRef.current ?? "")
        const chart = chartRef.current
        chart.timeScale().fitContent()

        for (const dataSeries of data) {
            chart.addSeries(typeOfSeries(dataSeries.type)).setData(dataSeries.data)
        }

    })

    useEffect(() => {
        if (!containerRef.current) return;

        const observer = new ResizeObserver(entries => {
            for (let entry of entries) {
                console.log("Chart width:", entry.contentRect.width);
                chartRef.current?.applyOptions({
                    width: entry.contentRect.width
                })
            }
        });

        observer.observe(containerRef.current);

        return () => observer.disconnect();   // cleanup
    });

    return (
        <div id="chart-container" ref={containerRef} className={`w-full h-[calc(100vh-theme(space.16))]`}></div>
    )
}