import React, { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell, ReferenceLine
} from 'recharts';

const W_CHANGE = 0.50;
const W_ATTENTION = 0.25;
const W_CAR = 0.25;

const COLORS = ['#4361ee', '#06d6a0', '#ef476f', '#ffd166', '#118ab2', '#7209b7', '#f72585'];

function LASChart({ filings }) {
  const data = useMemo(() => {
    if (!filings || filings.length === 0) return [];

    const latestByTicker = {};
    for (const f of filings) {
      if (f.las == null) continue;
      const t = f.ticker;
      if (!latestByTicker[t] || (f.report_date || '') > (latestByTicker[t].report_date || '')) {
        latestByTicker[t] = f;
      }
    }

    return Object.values(latestByTicker)
      .map(f => {
        const nc = f.norm_change != null ? Number(f.norm_change) : 0;
        const na = f.norm_attention != null ? Number(f.norm_attention) : 0;
        const ncar = f.norm_car != null ? Number(f.norm_car) : 0;

        return {
          ticker: f.ticker,
          las: Number(f.las),
          change_contrib: W_CHANGE * nc,
          attention_contrib: -(W_ATTENTION * na),
          car_contrib: W_CAR * ncar,
        };
      })
      .sort((a, b) => b.las - a.las);
  }, [filings]);

  if (data.length === 0) return null;

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload || !payload.length) return null;
    const d = data.find(x => x.ticker === label);
    if (!d) return null;
    return (
      <div style={{
        background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8,
        padding: '10px 14px', fontSize: 12, lineHeight: 1.7, boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
      }}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.ticker}</div>
        <div style={{ color: '#4361ee' }}>Change: +{d.change_contrib.toFixed(4)}</div>
        <div style={{ color: '#ef476f' }}>Attention: {d.attention_contrib.toFixed(4)}</div>
        <div style={{ color: '#06d6a0' }}>CAR: +{d.car_contrib.toFixed(4)}</div>
        <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: 4, marginTop: 4, fontWeight: 600 }}>
          LAS: {d.las.toFixed(4)}
        </div>
      </div>
    );
  };

  return (
    <div className="chart-card">
      <h3>LAS Breakdown by Ticker</h3>
      <p style={{ fontSize: 11, color: '#718096', marginTop: -10, marginBottom: 12 }}>
        Weighted components: Change (50%) - Attention (25%) + CAR (25%)
      </p>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }} stackOffset="sign">
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="ticker" tick={{ fontSize: 12, fontWeight: 600 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <ReferenceLine y={0} stroke="#a0aec0" />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 11 }}
            formatter={(value) => {
              const labels = {
                change_contrib: 'Change (50%)',
                attention_contrib: 'Attention (-25%)',
                car_contrib: 'CAR (25%)',
              };
              return labels[value] || value;
            }}
          />
          <Bar dataKey="change_contrib" stackId="las" fill="#4361ee" radius={[0, 0, 0, 0]} />
          <Bar dataKey="car_contrib" stackId="las" fill="#06d6a0" radius={[2, 2, 0, 0]} />
          <Bar dataKey="attention_contrib" stackId="las" fill="#ef476f" radius={[0, 0, 2, 2]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default LASChart;
