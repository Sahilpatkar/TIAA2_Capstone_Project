import React, { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';

function SimilarityChart({ filings }) {
  const data = useMemo(() => {
    if (!filings || filings.length === 0) return [];
    return filings
      .filter(f => f.similarity_cosine != null || f.similarity_jaccard != null)
      .map(f => ({
        name: `${f.ticker} ${f.report_date || ''}`.trim(),
        cosine: f.similarity_cosine != null ? Number(f.similarity_cosine) : null,
        jaccard: f.similarity_jaccard != null ? Number(f.similarity_jaccard) : null,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [filings]);

  if (data.length === 0) return null;

  return (
    <div className="chart-card">
      <h3>Similarity (Cosine vs Jaccard)</h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" height={60} />
          <YAxis tick={{ fontSize: 11 }} domain={[0, 1]} />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
            formatter={(val) => val != null ? val.toFixed(4) : '—'}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="cosine" name="Cosine" fill="#4361ee" radius={[4, 4, 0, 0]} />
          <Bar dataKey="jaccard" name="Jaccard" fill="#06d6a0" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default SimilarityChart;
