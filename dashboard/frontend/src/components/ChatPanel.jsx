import React, { useState, useRef, useEffect } from 'react';
import { sendChat } from '../api';

function ChatPanel({ tickers, activeClient }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEnd = useRef(null);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg = { role: 'user', content: text };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setInput('');
    setLoading(true);

    try {
      const history = updatedMessages.map(m => ({
        role: m.role,
        content: m.content,
      }));

      const data = await sendChat(text, tickers, history, {
        clientName: activeClient?.name,
        riskTolerance: activeClient?.risk_tolerance,
      });
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: data.response,
          isTemplate: data.is_template,
        },
      ]);
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: 'Sorry, there was an error processing your request.',
          isTemplate: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      <button
        className="chat-toggle"
        onClick={() => setOpen(!open)}
        title="Chat with your data"
      >
        {open ? '✕' : '💬'}
      </button>

      <div className={`chat-drawer ${open ? 'open' : ''}`}>
        <div className="chat-header">
          <h3>Chat with Data</h3>
          <button className="chat-close" onClick={() => setOpen(false)}>✕</button>
        </div>

        <div className="chat-messages">
          {messages.length === 0 && (
            <div style={{ color: '#718096', fontSize: 13, textAlign: 'center', padding: 20 }}>
              Ask questions about your portfolio's filing data, LAS scores, section changes, or anything LazyPrices-related.
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`chat-msg ${msg.role}`}>
              {msg.isTemplate && (
                <span className="template-badge">Template Mode</span>
              )}
              {msg.content}
            </div>
          ))}
          {loading && (
            <div className="chat-msg thinking">Thinking...</div>
          )}
          <div ref={messagesEnd} />
        </div>

        <div className="chat-input-row">
          <input
            className="chat-input"
            placeholder="Ask about your portfolio..."
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
          <button
            className="chat-send"
            onClick={handleSend}
            disabled={loading || !input.trim()}
          >
            Send
          </button>
        </div>
      </div>
    </>
  );
}

export default ChatPanel;
