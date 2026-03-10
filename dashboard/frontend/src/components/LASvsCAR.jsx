import React, { useMemo, useState } from 'react';
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ReferenceArea, Label, ZAxis,
} from 'recharts';

const COLORS = ['#4361ee', '#06d6a0', '#ef476f', '#ffd166', '#118ab2', '#7209b7', '#f72585'];

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={{
      background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8,
      padding: '8px 12px', fontSize: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
    }}>
      <strong>{d.ticker}</strong> ({d.reportDate})<br />
      LAS: {d.las.toFixed(4)}<br />
      CAR: {(d.car * 100).toFixed(2)}%
    </div>
  );
}

function LASvsCAR({ filings }) {
  const [showAll, setShowAll] = useState(false);

  const data = useMemo(() => {
    if (!filings || filings.length === 0) return [];

    const points = filings
      .filter(f => f.las != null && f.car != null)
      .map(f => ({
        ticker: f.ticker,
        las: Number(f.las),
        car: Number(f.car),
        reportDate: f.report_date || '',
      }));

    const latestByTicker = {};
    points.forEach(d => {
      if (!latestByTicker[d.ticker] || d.reportDate > latestByTicker[d.ticker]) {
        latestByTicker[d.ticker] = d.reportDate;
      }
    });

    return points.map(d => ({
      ...d,
      isLatest: d.reportDate === latestByTicker[d.ticker],
    }));
  }, [filings]);

  const tickers = useMemo(() => [...new Set(data.map(d => d.ticker))], [data]);

  const tickerColors = useMemo(() => {
    const map = {};
    tickers.forEach((t, i) => { map[t] = COLORS[i % COLORS.length]; });
    return map;
  }, [tickers]);

  const { latestGrouped, historicalGrouped } = useMemo(() => {
    const latest = {};
    const historical = {};
    data.forEach(d => {
      if (d.isLatest) {
        if (!latest[d.ticker]) latest[d.ticker] = [];
        latest[d.ticker].push(d);
      } else {
        if (!historical[d.ticker]) historical[d.ticker] = [];
        historical[d.ticker].push(d);
      }
    });
    return { latestGrouped: latest, historicalGrouped: historical };
  }, [data]);

  const visibleData = useMemo(() => {
    return showAll ? data : data.filter(d => d.isLatest);
  }, [data, showAll]);

  const { xDomain, yDomain } = useMemo(() => {
    if (visibleData.length === 0) return { xDomain: [0, 1], yDomain: [-0.1, 0.1] };
    const lasVals = visibleData.map(d => d.las);
    const carVals = visibleData.map(d => d.car);
    const xMin = Math.min(0, ...lasVals);
    const xMax = Math.max(1, ...lasVals);
    const yMin = Math.min(-0.05, ...carVals);
    const yMax = Math.max(0.05, ...carVals);
    const yPad = (yMax - yMin) * 0.15 || 0.02;
    return {
      xDomain: [Math.floor(xMin * 10) / 10, Math.ceil(xMax * 10) / 10],
      yDomain: [yMin - yPad, yMax + yPad],
    };
  }, [visibleData]);

  if (data.length === 0) return null;

  const labelStyle = { fontSize: 10, fill: '#a0aec0', fontStyle: 'italic' };

  const toggleBtnStyle = {
    fontSize: 11,
    padding: '3px 10px',
    borderRadius: 6,
    border: '1px solid #cbd5e0',
    background: showAll ? '#4361ee' : '#fff',
    color: showAll ? '#fff' : '#4a5568',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  };

  return (
    <div className="chart-card" style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0 }}>LAS vs CAR — Text Change vs Market Reaction</h3>
        <button style={toggleBtnStyle} onClick={() => setShowAll(v => !v)}>
          {showAll ? 'All History' : 'Current Only'}
        </button>
      </div>
      <ResponsiveContainer width="100%" height={340}>
        <ScatterChart margin={{ top: 20, right: 30, bottom: 15, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />

          <ReferenceArea x1={0.5} x2={xDomain[1]} y1={0} y2={yDomain[1]}
            fill="#06d6a0" fillOpacity={0.06} ifOverflow="hidden">
            <Label value="Important Change Detected" position="insideTopRight" style={labelStyle} />
          </ReferenceArea>
          <ReferenceArea x1={xDomain[0]} x2={0.5} y1={0} y2={yDomain[1]}
            fill="#ffd166" fillOpacity={0.06} ifOverflow="hidden">
            <Label value="Market Reacting to Something Else" position="insideTopLeft" style={labelStyle} />
          </ReferenceArea>
          <ReferenceArea x1={0.5} x2={xDomain[1]} y1={yDomain[0]} y2={0}
            fill="#ef476f" fillOpacity={0.06} ifOverflow="hidden">
            <Label value="Lazy Attention Opportunity" position="insideBottomRight" style={labelStyle} />
          </ReferenceArea>

          <XAxis
            type="number" dataKey="las" name="LAS" domain={xDomain}
            tick={{ fontSize: 11 }} tickFormatter={v => v.toFixed(1)}
          >
            <Label value="LAS" position="insideBottomRight" offset={-5} style={{ fontSize: 12, fill: '#718096' }} />
          </XAxis>
          <YAxis
            type="number" dataKey="car" name="CAR" domain={yDomain}
            tick={{ fontSize: 11 }} tickFormatter={v => `${(v * 100).toFixed(1)}%`}
          >
            <Label value="CAR" angle={-90} position="insideTopLeft" offset={10} style={{ fontSize: 12, fill: '#718096' }} />
          </YAxis>
          <ZAxis range={[60, 60]} />

          <ReferenceLine x={0.5} stroke="#a0aec0" strokeDasharray="6 4" />
          <ReferenceLine y={0} stroke="#a0aec0" strokeDasharray="6 4" />

          <Tooltip content={<CustomTooltip />} />

          {showAll && tickers.map(ticker => (
            historicalGrouped[ticker]?.length > 0 && (
              <Scatter
                key={`${ticker}-hist`}
                name={`${ticker} (history)`}
                data={historicalGrouped[ticker]}
                fill={tickerColors[ticker]}
                fillOpacity={0.25}
                strokeWidth={0}
              />
            )
          ))}

          {tickers.map(ticker => (
            latestGrouped[ticker]?.length > 0 && (
              <Scatter
                key={ticker}
                name={ticker}
                data={latestGrouped[ticker]}
                fill={tickerColors[ticker]}
                strokeWidth={1}
                stroke="#fff"
              />
            )
          ))}
        </ScatterChart>
      </ResponsiveContainer>

      {tickers.length > 1 && (
        <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 8, flexWrap: 'wrap' }}>
          {tickers.map(t => (
            <span key={t} style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: tickerColors[t], display: 'inline-block' }} />
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default LASvsCAR;
