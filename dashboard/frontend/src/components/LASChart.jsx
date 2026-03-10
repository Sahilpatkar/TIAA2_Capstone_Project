import React, { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell
} from 'recharts';

const COLORS = ['#4361ee', '#06d6a0', '#ef476f', '#ffd166', '#118ab2', '#7209b7', '#f72585'];

function LASChart({ filings }) {
  const data = useMemo(() => {
    if (!filings || filings.length === 0) return [];
    return filings
      .filter(f => f.las != null)
      .map(f => ({
        name: `${f.ticker} ${f.report_date || ''}`.trim(),
        ticker: f.ticker,
        las: Number(f.las),
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [filings]);

  const tickerColors = useMemo(() => {
    const unique = [...new Set(data.map(d => d.ticker))];
    const map = {};
    unique.forEach((t, i) => { map[t] = COLORS[i % COLORS.length]; });
    return map;
  }, [data]);

  if (data.length === 0) return null;

  return (
    <div className="chart-card">
      <h3>LAS by Filing</h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" height={60} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
            formatter={(val) => [val.toFixed(4), 'LAS']}
          />
          <Bar dataKey="las" radius={[4, 4, 0, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={tickerColors[entry.ticker]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default LASChart;
