import React, { useState, useEffect, useRef } from 'react';

const STAGES = ['pull', 'extract', 'embed', 'similarity', 'market', 'las', 'store', 'done'];

const STAGE_LABELS = {
  pull: 'Pull',
  extract: 'Extract',
  embed: 'Embed',
  similarity: 'Similarity',
  market: 'Market Data',
  las: 'LAS',
  store: 'Store',
  done: 'Done',
};

function stageIndex(stage) {
  const idx = STAGES.indexOf(stage);
  return idx >= 0 ? idx : -1;
}

function StageIndicator({ currentStage, status }) {
  const current = stageIndex(currentStage);
  return (
    <div className="pipeline-stages">
      {STAGES.map((s, i) => {
        let cls = 'stage-dot';
        if (status === 'completed' || status === 'failed') {
          cls += i <= current || status === 'completed' ? ' stage-complete' : '';
          if (status === 'failed' && i === current) cls += ' stage-failed';
        } else if (i < current) {
          cls += ' stage-complete';
        } else if (i === current) {
          cls += ' stage-active';
        }
        return (
          <React.Fragment key={s}>
            {i > 0 && <span className="stage-connector" />}
            <span className={cls} title={STAGE_LABELS[s]}>
              <span className="stage-label">{STAGE_LABELS[s]}</span>
            </span>
          </React.Fragment>
        );
      })}
    </div>
  );
}

/** Clean up a raw pipeline log message for executive display. */
function cleanSummaryMsg(msg) {
  // Strip leading whitespace and bracket prefix for cleaner display
  let clean = msg.replace(/^\s*\[\w+\]\s*/, '');
  // Remove internal file paths
  clean = clean.replace(/\/app\/data\/filings\/[^\s]+/g, '');
  // Remove CIK numbers from display
  clean = clean.replace(/\(CIK \d+\)/g, '');
  return clean.trim();
}

function PipelineLogPanel({ jobs, onClose, minimized, onToggleMinimize }) {
  const [showFullLogs, setShowFullLogs] = useState({});
  const logEndRef = useRef(null);

  useEffect(() => {
    if (!minimized && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [jobs, minimized]);

  if (!jobs || jobs.length === 0) return null;

  const toggleFullLogs = (jobId) => {
    setShowFullLogs(prev => ({ ...prev, [jobId]: !prev[jobId] }));
  };

  return (
    <div className={`pipeline-log-panel ${minimized ? 'minimized' : ''}`}>
      <div className="pipeline-log-header">
        <span className="pipeline-log-title">Pipeline</span>
        <span className="pipeline-log-actions">
          <button className="pipeline-log-btn" onClick={onToggleMinimize} title={minimized ? 'Expand' : 'Minimize'}>
            {minimized ? '\u25B2' : '\u25BC'}
          </button>
          <button className="pipeline-log-btn" onClick={onClose} title="Close">&times;</button>
        </span>
      </div>

      {!minimized && (
        <div className="pipeline-log-body">
          {jobs.map(job => {
            const isFull = showFullLogs[job.jobId];
            const summaryLogs = job.logs.filter(e => e.level === 'summary');
            const displayLogs = isFull ? job.logs : summaryLogs;
            const detailCount = job.logs.length - summaryLogs.length;

            return (
              <div key={job.jobId} className="pipeline-job-section">
                <div className="pipeline-job-header">
                  <span className="pipeline-job-tickers">{job.tickers.join(', ')}</span>
                  <span className={`pipeline-job-status status-${job.status}`}>
                    {job.status}
                  </span>
                </div>
                <StageIndicator currentStage={job.currentStage} status={job.status} />

                <div className="pipeline-log-area">
                  {displayLogs.map((entry, i) => (
                    <div
                      key={i}
                      className={`log-line ${entry.stage ? `log-stage-${entry.stage}` : ''} ${entry.level === 'detail' ? 'log-detail' : 'log-summary'}`}
                    >
                      {isFull && (
                        <span className="log-time">
                          {new Date(entry.ts * 1000).toLocaleTimeString()}
                        </span>
                      )}
                      <span className="log-msg">
                        {isFull ? entry.msg : cleanSummaryMsg(entry.msg)}
                      </span>
                    </div>
                  ))}
                  {job.status === 'running' && displayLogs.length === 0 && (
                    <div className="log-line log-waiting">Starting pipeline...</div>
                  )}
                  <div ref={logEndRef} />
                </div>

                {detailCount > 0 && (
                  <button
                    className="log-toggle-btn"
                    onClick={() => toggleFullLogs(job.jobId)}
                  >
                    {isFull
                      ? 'Show Summary'
                      : `Show Full Logs (${job.logs.length} entries)`}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default PipelineLogPanel;
