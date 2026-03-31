import React, { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell
} from 'recharts';

const COLORS = ['#4361ee', '#3a56d4', '#5a7cf7', '#7b9cff', '#2c47c4', '#6b8df5', '#4f6fe8'];

function SimilarityChart({ filings }) {
  const data = useMemo(() => {
    if (!filings || filings.length === 0) return [];

    const latestByTicker = {};
    for (const f of filings) {
      if (f.similarity_cosine == null) continue;
      const t = f.ticker;
      if (!latestByTicker[t] || (f.report_date || '') > (latestByTicker[t].report_date || '')) {
        latestByTicker[t] = f;
      }
    }

    return Object.values(latestByTicker)
      .map(f => ({
        ticker: f.ticker,
        changePct: Number(((1 - Number(f.similarity_cosine)) * 100).toFixed(2)),
      }))
      .sort((a, b) => b.changePct - a.changePct);
  }, [filings]);

  if (data.length === 0) return null;

  const chartHeight = Math.max(200, data.length * 32 + 40);

  const CustomTooltip = ({ active, payload }) => {
    if (!active || !payload || !payload.length) return null;
    const d = payload[0].payload;
    return (
      <div style={{
        background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8,
        padding: '8px 12px', fontSize: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
      }}>
        <div style={{ fontWeight: 700, marginBottom: 2 }}>{d.ticker}</div>
        <div>{d.changePct}% of filing language changed YoY</div>
      </div>
    );
  };

  return (
    <div className="chart-card">
      <h3>10-K Filing Change by Ticker</h3>
      <p style={{ fontSize: 11, color: '#718096', marginTop: -10, marginBottom: 12 }}>
        Percentage of filing language that changed year-over-year
      </p>
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart data={data} layout="vertical" margin={{ top: 5, right: 30, bottom: 5, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 11 }} unit="%" domain={[0, 'auto']} />
          <YAxis type="category" dataKey="ticker" tick={{ fontSize: 12, fontWeight: 600 }} width={45} />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="changePct" radius={[0, 4, 4, 0]} barSize={20}>
            {data.map((entry, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default SimilarityChart;
