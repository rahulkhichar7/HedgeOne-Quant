'use client'

import { useEffect, useId, useRef, useState } from "react";
import { Autocomplete, AutocompleteEmpty, AutocompleteInput, AutocompleteItem, AutocompleteList, AutocompletePopup, AutocompletePositioner } from "@/components/ui/autocomplete";
import { Button } from "@/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Chart, ChartData} from "@/components/chart";
import { CandlestickData } from "lightweight-charts";


const tags: Tag[] = [
  { id: "t1", value: "feature" },
  { id: "t2", value: "fix" },
  { id: "t3", value: "bug" },
  { id: "t4", value: "docs" },
  { id: "t5", value: "internal" },
  { id: "t6", value: "mobile" },
  { id: "c-accordion", value: "component: accordion" },
  { id: "c-alert-dialog", value: "component: alert dialog" },
  { id: "c-autocomplete", value: "component: autocomplete" },
  { id: "c-avatar", value: "component: avatar" },
  { id: "c-tooltip", value: "component: tooltip" },
];
const initialData = [
    { time: '2018-12-22', value: 32.51 },
    { time: '2018-12-23', value: 31.11 },
    { time: '2018-12-24', value: 27.02 },
    { time: '2018-12-25', value: 27.32 },
    { time: '2018-12-26', value: 25.17 },
    { time: '2018-12-27', value: 28.89 },
    { time: '2018-12-28', value: 25.46 },
    { time: '2018-12-29', value: 23.92 },
    { time: '2018-12-30', value: 22.68 },
    { time: '2018-12-31', value: 22.67 },
];

const chartOptions = { layout: { textColor: 'black', background: { type: 'solid', color: 'white' } } };
const ohclData = [
    { time: '2018-12-22', open: 75.16, high: 82.84, low: 36.16, close: 45.72 },
    { time: '2018-12-23', open: 45.12, high: 53.90, low: 45.12, close: 48.09 },
    { time: '2018-12-24', open: 60.71, high: 60.71, low: 53.39, close: 59.29 },
    { time: '2018-12-25', open: 68.26, high: 68.26, low: 59.04, close: 60.50 },
    { time: '2018-12-26', open: 67.71, high: 105.85, low: 66.67, close: 91.04 },
    { time: '2018-12-27', open: 91.04, high: 121.40, low: 82.70, close: 111.40 },
    { time: '2018-12-28', open: 111.51, high: 142.83, low: 103.34, close: 131.25 },
    { time: '2018-12-29', open: 131.33, high: 151.17, low: 77.68, close: 96.43 },
    { time: '2018-12-30', open: 106.33, high: 110.20, low: 90.39, close: 98.10 },
    { time: '2018-12-31', open: 109.87, high: 114.69, low: 85.66, close: 111.26 },
]

const data = [
    {
        label: "Series1",
        color: "blue",
        type: "LineSeries",
        data: initialData,
        other: ""
    },
    {
        label: "Series2",
        color: "black",
        type: "CandlesticksSeries",
        data: ohclData,
        other: ""
    }
]

// Fetch stock/index data here
function fetchData(name: string){
  return []
}

const default_state = {
  stocks: [
    {
      label: "Name",
      color: "blue",
      type:  "CandlesticksSeries",
      other:  "where did you apply this",
      data:  ohclData
    }
  ],
  indicators: [
    {
      label:  "Name",
      color:  "blue",
      other:     "where did you apply this",
      type:   "LineSeries",
      data:   initialData
    }
  ],
  strategies: [
    {
      label:  "Name",
      color:  "blue",
      other:     "where did you apply this",
      type:   "LineSeries", 
      data:   initialData
    }
  ]
}

export default function Home() {
  // const [state, setState] = useState({
  //   stocks: [] as ChartData[],
  //   indicators: [] as ChartData[],
  //   strategies: [] as ChartData[]
  // })
  const [state, setState] = useState(default_state)

  return (
    <div className="items-center bg-zinc-50 font-sans dark:bg-black">
      <div className="flex flex-row justify-left gap-2 m-1">
          <Button>Backtest</Button>
      </div>
      <ResizablePanelGroup
        direction="horizontal"
        className="h-full"
      >
        <ResizablePanel defaultSize={25}>
          <div className="h-full justify-left p-2">
            <div className="border bg-amber-50 p-2">
            <p>Stocks/Indices <Button>Add</Button></p>
              <ul>
                {state.stocks.map(stock =>
                  <li key={useId()}>{stock.label}</li>
                )}
              </ul>
            </div>
            <div className="border bg-amber-50 p-2">
              <p>Indicators <Button>Add</Button></p>
              <ul>
                {state.indicators.map(indicator =>
                  <li key={useId()}>{indicator.label}</li>
                )}
              </ul>
            </div>
            <div className="border bg-amber-50 p-2">
              <p>Strategies <Button>Add</Button></p>
              <ul>
                {state.strategies.map(strategy =>
                  <li key={useId()}>{strategy.label}</li>
                )}
              </ul>
            </div>
            {/* <span className="font-semibold">Sidebar</span> */}
          </div>
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize={75}>
          <div className="flex h-full items-center justify-center">
            <Chart data={[...state.stocks, ...state.indicators, ...state.strategies]}></Chart>
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
