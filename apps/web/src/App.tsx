import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { CinematicOverviewEffects } from './CinematicOverviewEffects';
import { mockDashboard } from './data/mock';
import {
  approveInvestigationAction,
  executeInvestigationAction,
  getDashboard,
  runInvestigation,
  submitReviewDecision,
} from './lib/api';
import type {
  AuditEvent,
  ConfidenceBand,
  DashboardData,
  DataSource,
  Incident,
  ProposedAction,
  ReviewDecision,
  ReviewItem,
  View,
} from './types';

const navigation: Array<{ view: View; label: string; short: string }> = [
  { view: 'overview', label: 'Overview', short: '01' },
  { view: 'reviews', label: 'Review queue', short: '02' },
  { view: 'incidents', label: 'Investigations', short: '03' },
  { view: 'audit', label: 'Audit log', short: '04' },
];

const pageMeta: Record<View, { eyebrow: string; title: string }> = {
  overview: { eyebrow: 'Matching operations', title: 'Overview' },
  reviews: { eyebrow: 'Human decisions', title: 'Review queue' },
  incidents: { eyebrow: 'Bounded agent actions', title: 'Investigations' },
  audit: { eyebrow: 'Tamper-evident history', title: 'Audit log' },
};

function pathToView(path: string): View {
  if (path.startsWith('/reviews')) return 'reviews';
  if (path.startsWith('/incidents')) return 'incidents';
  if (path.startsWith('/audit')) return 'audit';
  return 'overview';
}

function viewToPath(view: View): string {
  return view === 'overview' ? '/overview' : `/${view}`;
}

function formatTime(date: string): string {
  return new Intl.DateTimeFormat('en', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(date));
}

function formatDateTime(date: string): string {
  return new Intl.DateTimeFormat('en', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(date));
}

function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ');
}

function TinyArrow({ direction = 'right' }: { direction?: 'right' | 'up' | 'down' }) {
  const transform = direction === 'up' ? 'rotate(-45 8 8)' : direction === 'down' ? 'rotate(45 8 8)' : '';
  return (
    <svg className="tiny-arrow" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M3.5 8h8.75M9 4.75 12.25 8 9 11.25" transform={transform} />
    </svg>
  );
}

function StatusDot({ tone }: { tone: 'good' | 'warning' | 'danger' | 'neutral' }) {
  return <span className={`status-dot status-dot--${tone}`} aria-hidden="true" />;
}

function SourceBadge({ source }: { source: DataSource }) {
  const label = source === 'live' ? 'Live API' : source === 'connecting' ? 'Connecting' : 'Demo dataset';
  return (
    <span className={`source-badge source-badge--${source}`}>
      <StatusDot tone={source === 'live' ? 'good' : source === 'connecting' ? 'neutral' : 'warning'} />
      {label}
    </span>
  );
}

function ThemeGlyph({ dark }: { dark: boolean }) {
  return dark ? (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M15.8 12.9A6.8 6.8 0 0 1 7.1 4.2 6 6 0 1 0 15.8 13Z" />
    </svg>
  ) : (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10" r="3.1" />
      <path d="M10 2v1.5M10 16.5V18M2 10h1.5M16.5 10H18M4.35 4.35 5.4 5.4M14.6 14.6l1.05 1.05M15.65 4.35 14.6 5.4M5.4 14.6l-1.05 1.05" />
    </svg>
  );
}

interface SidebarProps {
  view: View;
  open: boolean;
  dark: boolean;
  source: DataSource;
  onNavigate: (view: View) => void;
  onClose: () => void;
  onTheme: () => void;
}

function Sidebar({ view, open, dark, source, onNavigate, onClose, onTheme }: SidebarProps) {
  return (
    <>
      <button
        className={cn('sidebar-scrim', open && 'is-visible')}
        aria-label="Close navigation"
        tabIndex={open ? 0 : -1}
        onClick={onClose}
      />
      <aside className={cn('sidebar', open && 'is-open')} aria-label="Primary navigation">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
          </span>
          <span className="brand-word">Catalog<span>Ops</span></span>
        </div>

        <nav className="primary-nav">
          {navigation.map((item) => (
            <button
              key={item.view}
              className={cn('nav-item', view === item.view && 'is-active')}
              aria-current={view === item.view ? 'page' : undefined}
              onClick={() => onNavigate(item.view)}
            >
              <span className="nav-index">{item.short}</span>
              <span>{item.label}</span>
              {item.view === 'incidents' && <span className="nav-count" aria-label="1 open incident">1</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="service-state">
            <div>
              <span className="service-label">Serving state</span>
              <strong>{source === 'live' ? 'Operational' : 'Local demonstration'}</strong>
            </div>
            <StatusDot tone={source === 'live' ? 'good' : 'warning'} />
          </div>
          <button className="theme-toggle" onClick={onTheme} aria-label={`Switch to ${dark ? 'light' : 'dark'} theme`}>
            <ThemeGlyph dark={dark} />
            <span>{dark ? 'Light theme' : 'Dark theme'}</span>
          </button>
          <div className="user-chip" aria-label="Signed in as Maya Chen, ML operations lead">
            <span className="avatar" aria-hidden="true">MC</span>
            <div>
              <strong>Maya Chen</strong>
              <span>ML operations lead</span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}

interface TopbarProps {
  view: View;
  data: DashboardData;
  source: DataSource;
  onMenu: () => void;
}

function Topbar({ view, data, source, onMenu }: TopbarProps) {
  return (
    <header className="topbar">
      <button className="menu-button" aria-label="Open navigation" onClick={onMenu}>
        <span /><span />
      </button>
      <div className="topbar-title">
        <span>{pageMeta[view].eyebrow}</span>
        <strong>{pageMeta[view].title}</strong>
      </div>
      <div className="topbar-meta">
        <span className="model-label">Model <strong>{data.modelVersion}</strong></span>
        <SourceBadge source={source} />
        <button className="icon-button" aria-label="Notifications, one unread">
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path d="M5.3 8.2a4.7 4.7 0 0 1 9.4 0c0 4.1 1.7 4.4 1.7 5.2H3.6c0-.8 1.7-1.1 1.7-5.2ZM8 15.4a2.2 2.2 0 0 0 4 0" />
          </svg>
          <span className="notification-dot" />
        </button>
      </div>
    </header>
  );
}

function ThroughputChart({ data }: { data: DashboardData['chart'] }) {
  const width = 760;
  const height = 264;
  const padX = 38;
  const padY = 25;
  const max = Math.max(...data.map((point) => point.throughput), 1) * 1.08;
  const step = (width - padX * 2) / Math.max(data.length - 1, 1);
  const y = (value: number) => height - padY - (value / max) * (height - padY * 2);
  const points = data.map((point, index) => `${padX + index * step},${y(point.throughput)}`).join(' ');
  const area = `M ${padX} ${height - padY} L ${points.replaceAll(',', ' ')} L ${width - padX} ${height - padY} Z`;
  const deploymentX = padX + step * 6.8;

  return (
    <div className="chart-wrap">
      <div className="chart-heading">
        <div>
          <span className="section-kicker">Seeded UI fixture · illustrative 24 hours</span>
          <h2>Example throughput telemetry—not a live API time series.</h2>
        </div>
        <div className="chart-legend" aria-label="Current chart value">
          <span><i className="legend-line" />Listings / hour</span>
          <strong>{data.at(-1)?.throughput ?? 0}</strong>
        </div>
      </div>
      <svg
        className="throughput-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-labelledby="throughput-title throughput-desc"
      >
        <title id="throughput-title">Illustrative listing inference throughput over 24 hours</title>
        <desc id="throughput-desc">
          Seeded interface fixture. Throughput peaks at {Math.max(...data.map((point) => point.throughput))} listings per hour and ends at {data.at(-1)?.throughput ?? 0}.
        </desc>
        <defs>
          <linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75, 1].map((ratio) => (
          <line key={ratio} x1={padX} x2={width - padX} y1={height - padY - ratio * (height - padY * 2)} y2={height - padY - ratio * (height - padY * 2)} className="grid-line" />
        ))}
        <path d={area} fill="url(#chart-fill)" />
        <polyline points={points} className="chart-line" />
        <line x1={deploymentX} x2={deploymentX} y1={18} y2={height - padY} className="deploy-line" />
        <text x={deploymentX + 8} y={32} className="deploy-label">Feed change</text>
        {data.map((point, index) => index % 2 === 0 && (
          <text key={point.time} x={padX + index * step} y={height - 5} textAnchor="middle" className="axis-label">{point.time}</text>
        ))}
        {data.map((point, index) => (
          <circle key={`${point.time}-point`} cx={padX + index * step} cy={y(point.throughput)} r="9" className="chart-hit" tabIndex={0}>
            <title>{point.time}: {point.throughput} listings/hour</title>
          </circle>
        ))}
      </svg>
      <details className="chart-data">
        <summary>View accessible chart data</summary>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Time</th><th>Listings/hour</th><th>Precision</th><th>Calibration error</th></tr></thead>
            <tbody>{data.map((point) => <tr key={point.time}><td>{point.time}</td><td>{point.throughput}</td><td>{point.precision}%</td><td>{point.calibration}%</td></tr>)}</tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

interface OverviewProps {
  data: DashboardData;
  source: DataSource;
  onNavigate: (view: View) => void;
  onPointerMove: (event: React.PointerEvent<HTMLElement>) => void;
}

function Overview({ data, source, onNavigate, onPointerMove }: OverviewProps) {
  const activeIncident = data.incidents.find((incident) => incident.status !== 'resolved');
  return (
    <div className="overview-page">
      <section className="editorial-stage" onPointerMove={onPointerMove}>
        <div className="stage-atmosphere" aria-hidden="true">
          <CinematicOverviewEffects />
          <span className="atmosphere-one" />
          <span className="atmosphere-two" />
          <span className="stage-grid" />
        </div>
        <div className="stage-topline">
          <SourceBadge source={source} />
          <span>Configurable demo policy · auto ≥ 0.85 · review 0.55–0.85 · reject &lt; 0.55</span>
        </div>
        <div className="stage-copy">
          <p className="hero-kicker"><span>01</span> Marketplace matching, under control</p>
          <h1>
            Every match<br />
            should survive<br />
            <em>scrutiny.</em>
          </h1>
          <div className="hero-subcopy">
            <p>
              CatalogOps turns uncertain product identity into measurable, reviewable decisions—then records exactly what changed and why.
            </p>
            <div className="hero-actions">
              <button className="button button--primary" onClick={() => onNavigate('reviews')}>
                Open review queue <TinyArrow />
              </button>
              <button className="button button--ghost" onClick={() => onNavigate('incidents')}>
                Inspect active incident
              </button>
            </div>
          </div>
        </div>
        <div className="stage-system-line" aria-label="Current decision pipeline state">
          <span className="pipeline-provenance">{source === 'live' ? 'Live metrics summary' : 'Seeded UI fixture'}</span>
          <div>
            <span>Retrieve</span>
            <strong>{data.pipeline.recallAtK}</strong>
            <small>Recall@5</small>
          </div>
          <i aria-hidden="true" />
          <div>
            <span>Score</span>
            <strong>{data.pipeline.precision}</strong>
            <small>Baseline precision ≥ 0.85</small>
          </div>
          <i aria-hidden="true" />
          <div>
            <span>Route</span>
            <strong>{data.pipeline.reviewRate}</strong>
            <small>Human review</small>
          </div>
          <i aria-hidden="true" />
          <div>
            <span>Record</span>
            <strong>{data.pipeline.decisionCoverage}</strong>
            <small>Decision coverage</small>
          </div>
        </div>
      </section>

      <section className="metric-band" aria-labelledby="system-pulse-title">
        <div className="section-intro">
          <span className="section-number">02</span>
          <div>
            <p className="section-kicker">System pulse</p>
            <h2 id="system-pulse-title">Safe enough to automate.<br />Specific enough to challenge.</h2>
          </div>
          <p>{source === 'live' ? `Metrics are mapped from ${data.datasetLabel}; the 24-hour chart below remains an illustrative UI fixture.` : 'These are seeded demonstration values, not published WDC benchmark results.'}</p>
        </div>
        <div className="metric-row">
          {data.metrics.map((metric) => (
            <article className="metric-item" key={metric.label}>
              <div className="metric-label"><span>{metric.label}</span><StatusDot tone={metric.tone === 'warning' ? 'warning' : 'good'} /></div>
              <strong>{metric.value}</strong>
              <div className="metric-detail"><span>{metric.detail}</span>{metric.delta && <b className={metric.tone === 'warning' ? 'is-warning' : ''}>{metric.delta}</b>}</div>
            </article>
          ))}
        </div>
      </section>

      <section className="overview-grid">
        <ThroughputChart data={data.chart} />
        <aside className="calibration-panel" aria-labelledby="calibration-title">
          <div className="panel-topline">
            <span className="section-kicker">{activeIncident ? 'Active quality signal' : 'Monitoring state'}</span>
            <span className={`severity severity--${activeIncident?.severity ?? 'medium'}`}>{activeIncident?.severity ?? 'Stable'}</span>
          </div>
          <div className="calibration-reading">
            <span>{activeIncident?.metric ?? 'Open quality incidents'}</span>
            <strong>{activeIncident?.currentValue ?? '0'}</strong>
            <small>{activeIncident ? `expected ${activeIncident.baselineValue}` : 'all configured signals in bounds'}</small>
          </div>
          <div className="calibration-scale" aria-label={activeIncident ? `${activeIncident.metric}: observed ${activeIncident.currentValue}, expected ${activeIncident.baselineValue}` : 'No active quality incident'}>
            <span style={{ '--scale': '68%' } as CSSProperties} />
            <i style={{ left: '50%' }}><small>expected</small></i>
          </div>
          <h2 id="calibration-title">{activeIncident?.title ?? 'No active intervention is required.'}</h2>
          <p>{activeIncident?.summary ?? 'Quality monitors have not opened an incident for the connected evidence window.'}</p>
          {activeIncident && <button className="text-link" onClick={() => onNavigate('incidents')}>Read agent investigation <TinyArrow /></button>}
        </aside>
      </section>

      <section className="decision-preview">
        <div className="decision-preview-copy">
          <span className="section-number">03</span>
          <p className="section-kicker">One decision, fully exposed</p>
          <h2>Not a score.<br />A case you can inspect.</h2>
          <p>Reviewers see every agreement, contradiction, missing identifier, and model signal before their decision becomes training evidence.</p>
          <button className="text-link" onClick={() => onNavigate('reviews')}>Review {data.reviews.filter((item) => item.decision === 'pending').length} pending cases <TinyArrow /></button>
        </div>
        <ReviewEvidencePreview item={data.reviews[0]} />
      </section>
    </div>
  );
}

function ReviewEvidencePreview({ item }: { item?: ReviewItem }) {
  if (!item) return null;
  return (
    <div className="evidence-preview">
      <div className="evidence-preview-head">
        <div><span>Seller listing · {item.listingId}</span><strong>{item.listingTitle}</strong></div>
        <span className="market-chip">{item.marketplace}</span>
      </div>
      <div className="match-bridge">
        <span><i /> baseline score</span>
        <strong>{Math.round(item.confidence * 1000) / 10}%</strong>
      </div>
      <div className="canonical-preview">
        <span>Canonical product · {item.canonicalId}</span>
        <strong>{item.canonicalTitle}</strong>
      </div>
      <div className="signal-ribbon">
        {item.signals.slice(0, 3).map((signal) => (
          <div key={signal.label}><span>{signal.label}</span><strong>{Math.round(signal.score * 100)}%</strong></div>
        ))}
      </div>
    </div>
  );
}

function ConfidencePill({ band, score }: { band: ConfidenceBand; score: number }) {
  return <span className={`confidence confidence--${band}`}><i />{(score * 100).toFixed(1)}%</span>;
}

interface ReviewViewProps {
  data: DashboardData;
  selectedId: string;
  busyId: string | null;
  onSelect: (id: string) => void;
  onDecision: (item: ReviewItem, decision: ReviewDecision) => void;
}

function ReviewView({ data, selectedId, busyId, onSelect, onDecision }: ReviewViewProps) {
  const [filter, setFilter] = useState<'pending' | 'all'>('pending');
  const [query, setQuery] = useState('');
  const selected = data.reviews.find((item) => item.id === selectedId) ?? data.reviews[0];
  const visible = data.reviews.filter((item) => {
    const matchesFilter = filter === 'all' || item.decision === 'pending';
    const needle = query.trim().toLowerCase();
    return matchesFilter && (!needle || `${item.listingTitle} ${item.seller} ${item.id}`.toLowerCase().includes(needle));
  });

  return (
    <div className="utility-page review-page">
      <header className="utility-heading">
        <div>
          <p className="hero-kicker"><span>02</span> Human decision boundary</p>
          <h1>{data.reviews.filter((item) => item.decision === 'pending').length} cases between<br /><em>confidence and consequence.</em></h1>
        </div>
        <div className="policy-note">
          <span>Configurable demo policy</span>
          <strong>Auto ≥ 0.85 · Review 0.55–0.85 · Reject &lt; 0.55</strong>
          <small>Serving {data.modelVersion}</small>
        </div>
      </header>

      <div className="queue-toolbar">
        <div className="segmented-control" aria-label="Queue status filter">
          <button className={filter === 'pending' ? 'is-active' : ''} onClick={() => setFilter('pending')}>Pending <span>{data.reviews.filter((item) => item.decision === 'pending').length}</span></button>
          <button className={filter === 'all' ? 'is-active' : ''} onClick={() => setFilter('all')}>All cases</button>
        </div>
        <label className="search-field">
          <span className="sr-only">Search review queue</span>
          <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.8" cy="8.8" r="5.4" /><path d="m13 13 4 4" /></svg>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search ID, seller, or title" />
        </label>
        <span className="shortcut-hint"><kbd>J</kbd><kbd>K</kbd> navigate · <kbd>A</kbd> match · <kbd>N</kbd> no match</span>
      </div>

      <div className="review-workspace">
        <section className="queue-list" aria-label="Review cases">
          <div className="queue-columns" aria-hidden="true"><span>Listing / proposed product</span><span>Confidence</span><span>Age</span></div>
          {visible.length ? visible.map((item) => (
            <button
              key={item.id}
              className={cn('queue-row', selected?.id === item.id && 'is-selected', item.decision !== 'pending' && 'is-decided')}
              onClick={() => onSelect(item.id)}
              aria-pressed={selected?.id === item.id}
            >
              <span className="row-main">
                <span className="row-overline"><b>{item.marketplace}</b>{item.seller} · {item.id}</span>
                <strong>{item.listingTitle}</strong>
                <small>→ {item.canonicalTitle}</small>
              </span>
              <ConfidencePill band={item.band} score={item.confidence} />
              <span className="row-age">{item.decision === 'pending' ? `${item.ageMinutes}m` : item.decision.replace('_', ' ')}</span>
            </button>
          )) : (
            <div className="empty-state"><strong>No cases found</strong><span>Try changing the status filter or search terms.</span></div>
          )}
        </section>
        {selected && <EvidenceInspector item={selected} modelVersion={data.modelVersion} busy={busyId === selected.id} onDecision={onDecision} />}
      </div>
    </div>
  );
}

function EvidenceInspector({ item, modelVersion, busy, onDecision }: { item: ReviewItem; modelVersion: string; busy: boolean; onDecision: (item: ReviewItem, decision: ReviewDecision) => void }) {
  const alternatives = [
    { rank: 2, title: item.canonicalTitle.replace(/Black|Cream|Purple|170mm/g, 'alternate variant'), score: Math.max(item.confidence - 0.08, 0.5) },
    { rank: 3, title: `${item.canonicalTitle.split(' ').slice(0, 5).join(' ')} · adjacent model`, score: Math.max(item.confidence - 0.19, 0.38) },
  ];
  return (
    <aside className="evidence-inspector" aria-label={`Evidence for ${item.id}`}>
      <div className="inspector-sticky-head">
        <div>
          <span className="section-kicker">Evidence inspector · {item.id}</span>
          <h2>Candidate rank #1</h2>
        </div>
        <div className="confidence-orbit" aria-label={`${(item.confidence * 100).toFixed(1)} percent confidence`} style={{ '--score': `${item.confidence * 360}deg` } as CSSProperties}>
          <span>{(item.confidence * 100).toFixed(1)}<small>%</small></span>
        </div>
      </div>

      <p className="decision-reason">{item.reason}</p>
      <div className="record-comparison">
        <div>
          <span>Seller listing · {item.listingId}</span>
          <strong>{item.listingTitle}</strong>
          <small>{item.seller} · source locale {item.marketplace}</small>
        </div>
        <div>
          <span>Canonical candidate · {item.canonicalId}</span>
          <strong>{item.canonicalTitle}</strong>
          <small>Canonical catalog entity · retrieved rank 1</small>
        </div>
      </div>

      <div className="subsection-head"><h3>Field comparison</h3><span>{item.fields.filter((field) => field.status === 'match').length}/{item.fields.length} agree</span></div>
      <div className="field-table" role="table" aria-label="Compared product fields">
        {item.fields.map((field) => (
          <div className={`field-row field-row--${field.status}`} role="row" key={field.label}>
            <span role="cell"><i />{field.label}</span>
            <span role="cell">{field.listing}</span>
            <span role="cell">{field.candidate}</span>
          </div>
        ))}
      </div>

      <div className="subsection-head"><h3>Decision evidence</h3><span>Baseline scorer · {modelVersion}</span></div>
      <div className="signal-list">
        {item.signals.map((signal) => (
          <div className="signal-row" key={signal.label}>
            <span><strong>{signal.label}</strong><small>{signal.value}</small></span>
            <span className={`signal-bar signal-bar--${signal.tone}`}><i style={{ width: `${Math.max(signal.score * 100, 3)}%` }} /></span>
            <b>{Math.round(signal.score * 100)}%</b>
          </div>
        ))}
      </div>

      <details className="alternatives">
        <summary>Other retrieved candidates <span>2</span></summary>
        {alternatives.map((alternative) => (
          <div key={alternative.rank}><span>#{alternative.rank}</span><strong>{alternative.title}</strong><b>{(alternative.score * 100).toFixed(1)}%</b></div>
        ))}
      </details>

      <div className="provenance-line">
        <span>Run demo-2026-09-01-04</span><span>{item.canonicalId}</span><span>trace 7ac2…10e</span>
      </div>
      <div className="decision-bar">
        {item.decision === 'pending' ? (
          <>
            <button className="button button--primary button--compact" disabled={busy} onClick={() => onDecision(item, 'match')}>{busy ? 'Recording…' : 'Confirm match'} <kbd>A</kbd></button>
            <button className="button button--danger-quiet button--compact" disabled={busy} onClick={() => onDecision(item, 'no_match')}>No match <kbd>N</kbd></button>
            <button className="button button--quiet button--compact" disabled={busy} onClick={() => onDecision(item, 'skipped')}>Skip <kbd>S</kbd></button>
          </>
        ) : (
          <div className="decision-complete"><StatusDot tone="good" /><span>Decision recorded: <strong>{item.decision.replace('_', ' ')}</strong></span></div>
        )}
      </div>
    </aside>
  );
}

interface IncidentsViewProps {
  data: DashboardData;
  selectedActionId: string;
  approvalChecked: boolean;
  onSelectAction: (id: string) => void;
  onApprovalCheck: (value: boolean) => void;
  onApprove: (incident: Incident, action: ProposedAction) => void;
  onExecute: (incident: Incident, action: ProposedAction) => void;
  actionBusy: 'approving' | 'executing' | null;
}

function IncidentsView({ data, selectedActionId, approvalChecked, onSelectAction, onApprovalCheck, onApprove, onExecute, actionBusy }: IncidentsViewProps) {
  const incident = data.incidents.find((entry) => entry.status !== 'resolved') ?? data.incidents[0];
  const action = incident?.proposedActions.find((entry) => entry.id === selectedActionId) ?? incident?.proposedActions[0];
  if (!incident) return <div className="empty-state"><strong>No incidents</strong><span>Monitoring has not opened an incident.</span></div>;

  return (
    <div className="utility-page incident-page">
      <header className="incident-heading">
        <div>
          <p className="hero-kicker"><span>03</span> Evidence-bound intervention</p>
          <h1>One action is waiting<br />for a <em>human.</em></h1>
        </div>
        <div className="incident-reading">
          <span>{incident.metric}</span>
          <strong>{incident.currentValue}</strong>
          <small>baseline {incident.baselineValue}</small>
        </div>
      </header>

      <div className="incident-layout">
        <main className="investigation-body">
          <div className="incident-titleline">
            <div><span className={`severity severity--${incident.severity}`}>{incident.severity}</span><span>{incident.id} · opened {formatDateTime(incident.startedAt)}</span></div>
            <span className="incident-status"><StatusDot tone={incident.status === 'resolved' ? 'good' : 'warning'} />{incident.status.replace('_', ' ')}</span>
          </div>
          <h2>{incident.title}</h2>
          <p className="incident-summary">{incident.summary}</p>

          <div className="investigation-label"><span>AI-generated analysis</span><small>Evidence may be incomplete. Human review required before execution.</small></div>
          <ol className="investigation-timeline">
            <li>
              <span className="timeline-index">01</span>
              <div><strong>Trigger</strong><p>{incident.metric} moved to {incident.currentValue} against an expected {incident.baselineValue}.</p><small>Quality monitor · {formatTime(incident.startedAt)} UTC</small></div>
            </li>
            <li>
              <span className="timeline-index">02</span>
              <div><strong>Inspect</strong><p>Collected incident metrics, current model identity, review-queue state, and known model-card limitations.</p><small>Bounded evidence collection · no write actions</small></div>
            </li>
            <li>
              <span className="timeline-index">03</span>
              <div><strong>Assess</strong><p>Checked the proposed action against the active {data.modelVersion} artifact and configured decision policy.</p><small>Recommendation only · execution blocked</small></div>
            </li>
            <li>
              <span className="timeline-index">04</span>
              <div><strong>Findings</strong><ul>{incident.findings.map((finding) => <li key={finding}>{finding}</li>)}</ul></div>
            </li>
          </ol>

          <section className="proposals" aria-labelledby="proposal-title">
            <div className="subsection-head"><h3 id="proposal-title">Proposed actions</h3><span>Select one for approval</span></div>
            {incident.proposedActions.map((proposal) => (
              <button
                key={proposal.id}
                className={cn('proposal-row', action?.id === proposal.id && 'is-selected')}
                aria-pressed={action?.id === proposal.id}
                onClick={() => onSelectAction(proposal.id)}
              >
                <span className="proposal-radio"><i /></span>
                <span><strong>{proposal.label}</strong><small>{proposal.description}</small></span>
                <span><b>{proposal.impact}</b><small>{proposal.reversible ? 'Reversible' : 'Creates records only'}</small></span>
              </button>
            ))}
          </section>
        </main>

        {action && (
          <aside className="approval-panel" aria-labelledby="approval-title">
            <span className="section-kicker">Approval checkpoint</span>
            <h2 id="approval-title">Review the exact production diff.</h2>
            <div className="policy-diff">
              <span>{action.type === 'threshold' ? 'matching_thresholds' : action.type === 'rollback' ? 'active_model' : 'review_queue'}</span>
              {action.type === 'threshold' ? (
                <div><del>current policy</del><TinyArrow /><ins>{action.impact}</ins></div>
              ) : action.type === 'rollback' ? (
                <div><del>{data.modelVersion}</del><TinyArrow /><ins>{action.label.replace('Rollback model to ', '').replace('Rollback baseline scorer to ', '')}</ins></div>
              ) : (
                <div><del>0 new reviews</del><TinyArrow /><ins>{action.impact}</ins></div>
              )}
            </div>
            <dl className="approval-facts">
              <div><dt>Scope</dt><dd>{incident.metric} · {incident.id}</dd></div>
              <div><dt>Expected impact</dt><dd>{action.impact}</dd></div>
              <div><dt>Duration</dt><dd>{action.type === 'threshold' ? 'Until verified or reverted' : action.type === 'review_batch' ? 'One-time batch' : 'Until next approved deploy'}</dd></div>
              <div><dt>Rollback</dt><dd>{action.reversible ? 'One-click revert to current state' : 'Not applicable'}</dd></div>
              <div><dt>Required role</dt><dd>ML operations lead</dd></div>
            </dl>
            <div className="guardrail"><StatusDot tone="good" /><span><strong>{incident.status === 'approved' ? 'Human approval recorded' : 'Policy check passed'}</strong><small>{incident.status === 'approved' ? 'Execution remains a separate operator action.' : 'Agent cannot execute without this approval.'}</small></span></div>
            {incident.status !== 'approved' && incident.status !== 'resolved' && (
              <>
                <label className="approval-checkbox">
                  <input type="checkbox" checked={approvalChecked} onChange={(event) => onApprovalCheck(event.target.checked)} />
                  <span>I reviewed scope, impact, and rollback plan.</span>
                </label>
                <button className="button button--primary approval-button" disabled={!approvalChecked || actionBusy !== null} onClick={() => onApprove(incident, action)}>
                  {actionBusy === 'approving' ? 'Recording approval…' : `Approve ${action.type.replace('_', ' ')}`}
                </button>
              </>
            )}
            {incident.status === 'approved' && (
              <div className="execution-step">
                <span className="section-kicker">Separate execution step</span>
                <p>Approval is already recorded. Execution applies the reviewed diff and writes a separate audit event.</p>
                <button className="button button--primary approval-button" disabled={actionBusy !== null || !incident.investigationId && data.datasetLabel !== 'Demo dataset'} onClick={() => onExecute(incident, action)}>
                  {actionBusy === 'executing' ? 'Executing action…' : 'Execute approved action'}
                </button>
              </div>
            )}
            {incident.status === 'resolved' && <div className="execution-complete"><StatusDot tone="good" /><span><strong>Action executed</strong><small>Verification and audit records are available in the ledger.</small></span></div>}
            <p className="approval-footnote">Live mode appends approval to a hash-chained audit log before execution. Demo mode changes local state only.</p>
          </aside>
        )}
      </div>
    </div>
  );
}

function AuditView({ data }: { data: DashboardData }) {
  const [query, setQuery] = useState('');
  const [actor, setActor] = useState<'all' | AuditEvent['actorType']>('all');
  const visible = data.audit.filter((event) => {
    const actorMatches = actor === 'all' || event.actorType === actor;
    const needle = query.trim().toLowerCase();
    return actorMatches && (!needle || `${event.action} ${event.actor} ${event.target} ${event.detail}`.toLowerCase().includes(needle));
  });

  const exportAudit = () => {
    const blob = new Blob([JSON.stringify(visible, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'catalogops-audit-demo.json';
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="utility-page audit-page">
      <header className="utility-heading audit-heading">
        <div>
          <p className="hero-kicker"><span>04</span> Tamper-evident decision history</p>
          <h1>Nothing changes<br /><em>quietly.</em></h1>
        </div>
        <p>Every model, reviewer, agent, and policy action is tied to evidence, an actor, and a tamper-evident hash.</p>
      </header>

      <div className="audit-toolbar">
        <label className="search-field search-field--wide">
          <span className="sr-only">Search audit log</span>
          <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.8" cy="8.8" r="5.4" /><path d="m13 13 4 4" /></svg>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search action, actor, object, or evidence" />
        </label>
        <label className="select-field">
          <span className="sr-only">Filter by actor type</span>
          <select value={actor} onChange={(event) => setActor(event.target.value as typeof actor)}>
            <option value="all">All actors</option>
            <option value="human">Human</option>
            <option value="agent">Agent</option>
            <option value="system">System</option>
          </select>
        </label>
        <button className="button button--quiet button--compact" onClick={exportAudit}>Export JSON</button>
      </div>

      <div className="audit-table-wrap">
        <table className="audit-table">
          <thead><tr><th>Timestamp</th><th>Actor</th><th>Action / object</th><th>Evidence</th><th>Outcome</th><th>Event hash</th></tr></thead>
          <tbody>
            {visible.map((event) => (
              <tr key={event.id}>
                <td><time dateTime={event.timestamp}>{formatDateTime(event.timestamp)}</time><small>{event.id}</small></td>
                <td><strong>{event.actor}</strong><span className={`actor-type actor-type--${event.actorType}`}>{event.actorType}</span></td>
                <td><strong>{event.action.replaceAll('_', ' ')}</strong><small>{event.target}</small></td>
                <td>{event.detail}</td>
                <td><span className={`outcome outcome--${event.outcome}`}><i />{event.outcome}</span></td>
                <td><code>{event.hash}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!visible.length && <div className="empty-state"><strong>No events found</strong><span>Try broadening your search or actor filter.</span></div>}
      </div>
      <div className={`audit-integrity audit-integrity--${data.auditIntegrity.status}`}>
        <StatusDot tone={data.auditIntegrity.status === 'verified' ? 'good' : data.auditIntegrity.status === 'invalid' ? 'danger' : 'neutral'} />
        <span>
          <strong>{data.auditIntegrity.status === 'verified' ? 'Chain integrity verified by API' : data.auditIntegrity.status === 'invalid' ? 'Audit chain verification failed' : 'Demo events are not cryptographically verified'}</strong>
          <small>{data.auditIntegrity.status === 'verified' ? `${data.auditIntegrity.checkedEvents} events checked · head ${data.auditIntegrity.headHash?.slice(0, 10)}…` : `Verification unavailable in demo mode · refreshed ${formatTime(data.lastUpdated)} UTC`}</small>
        </span>
      </div>
    </div>
  );
}

function App() {
  const [view, setView] = useState<View>(() => pathToView(window.location.pathname));
  const [data, setData] = useState<DashboardData>(mockDashboard);
  const [source, setSource] = useState<DataSource>('connecting');
  const [navOpen, setNavOpen] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem('catalogops-theme') === 'dark' || (!localStorage.getItem('catalogops-theme') && window.matchMedia('(prefers-color-scheme: dark)').matches));
  const [selectedReviewId, setSelectedReviewId] = useState(mockDashboard.reviews[0]?.id ?? '');
  const [selectedActionId, setSelectedActionId] = useState(mockDashboard.incidents[0]?.proposedActions[0]?.id ?? '');
  const [approvalChecked, setApprovalChecked] = useState(false);
  const [reviewBusyId, setReviewBusyId] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<'approving' | 'executing' | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    let active = true;
    getDashboard()
      .then((next) => {
        if (!active) return;
        setData(next);
        setSource('live');
        setSelectedReviewId(next.reviews[0]?.id ?? '');
        setSelectedActionId(next.incidents.find((incident) => incident.status !== 'resolved')?.proposedActions[0]?.id ?? '');
      })
      .catch(() => {
        if (!active) return;
        setData({ ...mockDashboard, lastUpdated: new Date().toISOString() });
        setSource('demo');
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    localStorage.setItem('catalogops-theme', dark ? 'dark' : 'light');
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#0b0c10' : '#f6f7f8');
  }, [dark]);

  useEffect(() => {
    const onPopState = () => setView(pathToView(window.location.pathname));
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const notify = (message: string) => {
    setToast(message);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3600);
  };

  const navigate = (next: View) => {
    setView(next);
    setNavOpen(false);
    const path = viewToPath(next);
    if (window.location.pathname !== path) window.history.pushState({}, '', path);
    window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  };

  const addAuditEvent = (event: Omit<AuditEvent, 'id' | 'timestamp' | 'hash'>) => {
    const suffix = Math.random().toString(16).slice(2, 6);
    setData((current) => ({
      ...current,
      audit: [{ ...event, id: `AUD-DEMO-${suffix.toUpperCase()}`, timestamp: new Date().toISOString(), hash: `sha256:demo…${suffix}` }, ...current.audit],
    }));
  };

  const handleReviewDecision = (item: ReviewItem, decision: ReviewDecision) => {
    if (reviewBusyId) return;
    const chooseNext = (reviews: ReviewItem[]) => {
      const currentIndex = reviews.findIndex((review) => review.id === item.id);
      const next = reviews.slice(currentIndex + 1).find((review) => review.decision === 'pending');
      if (next) setSelectedReviewId(next.id);
    };
    const applyLocalDecision = (verifiedByApi: boolean) => {
      setData((current) => ({
        ...current,
        auditIntegrity: verifiedByApi ? { ...current.auditIntegrity, status: 'unverified' } : current.auditIntegrity,
        reviews: current.reviews.map((review) => review.id === item.id ? { ...review, decision } : review),
      }));
      chooseNext(data.reviews);
    };

    if (source !== 'live') {
      applyLocalDecision(false);
      addAuditEvent({
        actor: 'Maya Chen', actorType: 'human', action: decision === 'match' ? 'APPROVED_MATCH' : decision === 'no_match' ? 'REJECTED_MATCH' : 'SKIPPED_REVIEW',
        target: item.id, detail: `Decision recorded for ${item.listingId} → ${item.canonicalId}`, outcome: 'success',
      });
      notify(`${item.id}: ${decision.replace('_', ' ')} recorded in demo state`);
      return;
    }

    setReviewBusyId(item.id);
    void submitReviewDecision(item, decision)
      .then(async () => {
        try {
          const refreshed = await getDashboard();
          setData(refreshed);
          chooseNext(refreshed.reviews);
          notify(`${item.id}: decision and audit event recorded by API`);
        } catch {
          applyLocalDecision(true);
          notify(`${item.id}: API recorded the decision; audit verification needs a refresh`);
        }
      })
      .catch(() => notify(`${item.id}: API rejected the decision; no local success was recorded`))
      .finally(() => setReviewBusyId(null));
  };

  useEffect(() => {
    if (view !== 'reviews') return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes((event.target as HTMLElement).tagName)) return;
      const pending = data.reviews.filter((item) => item.decision === 'pending');
      const index = Math.max(pending.findIndex((item) => item.id === selectedReviewId), 0);
      if (event.key.toLowerCase() === 'j' && pending[index + 1]) setSelectedReviewId(pending[index + 1].id);
      if (event.key.toLowerCase() === 'k' && pending[index - 1]) setSelectedReviewId(pending[index - 1].id);
      const selected = data.reviews.find((item) => item.id === selectedReviewId);
      if (!selected || selected.decision !== 'pending') return;
      if (event.key.toLowerCase() === 'a') handleReviewDecision(selected, 'match');
      if (event.key.toLowerCase() === 'n') handleReviewDecision(selected, 'no_match');
      if (event.key.toLowerCase() === 's') handleReviewDecision(selected, 'skipped');
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  const handleApprove = (incident: Incident, action: ProposedAction) => {
    const recordDemoApproval = (investigationId?: string) => {
      setData((current) => ({
        ...current,
        incidents: current.incidents.map((entry) => entry.id === incident.id ? { ...entry, investigationId: investigationId ?? entry.investigationId, status: 'approved' } : entry),
      }));
      addAuditEvent({
        actor: 'Maya Chen', actorType: 'human', action: `APPROVED_${action.type.toUpperCase()}`,
        target: incident.id, detail: `${action.label}; ${action.impact}`, outcome: 'success',
      });
      setApprovalChecked(false);
      notify(`${action.label} approved; execution is still required`);
    };
    if (source !== 'live') {
      recordDemoApproval(incident.investigationId);
      return;
    }
    setActionBusy('approving');
    void (async () => {
      const investigationId = incident.investigationId ?? (await runInvestigation(incident.id, action)).id;
      await approveInvestigationAction(investigationId, action);
      try {
        setData(await getDashboard());
        setApprovalChecked(false);
        notify(`${action.label} approved by API; execution is still required`);
      } catch {
        setData((current) => ({
          ...current,
          auditIntegrity: { ...current.auditIntegrity, status: 'unverified' },
          incidents: current.incidents.map((entry) => entry.id === incident.id ? { ...entry, investigationId, status: 'approved' } : entry),
        }));
        setApprovalChecked(false);
        notify(`${action.label} approved by API; audit verification needs a refresh`);
      }
    })().catch(() => notify('The live API did not record approval; no action can execute.')).finally(() => setActionBusy(null));
  };

  const handleExecute = (incident: Incident, action: ProposedAction) => {
    const recordDemoExecution = () => {
      setData((current) => ({
        ...current,
        incidents: current.incidents.map((entry) => entry.id === incident.id ? { ...entry, status: 'resolved' } : entry),
      }));
      addAuditEvent({
        actor: 'Maya Chen', actorType: 'human', action: `EXECUTED_${action.type.toUpperCase()}`,
        target: incident.id, detail: `Applied approved action: ${action.label}`, outcome: 'success',
      });
      notify(`${action.label} executed; verification event created`);
    };
    if (source !== 'live') {
      recordDemoExecution();
      return;
    }
    if (!incident.investigationId) {
      notify('Execution blocked: the approved investigation ID is missing.');
      return;
    }
    setActionBusy('executing');
    void executeInvestigationAction(incident.investigationId)
      .then(async () => {
        try {
          const refreshed = await getDashboard();
          setData(refreshed);
          notify(
            refreshed.auditIntegrity.status === 'verified'
              ? `${action.label} executed by API; audit chain reverified`
              : `${action.label} executed by API; audit chain verification failed`,
          );
        } catch {
          setData((current) => ({
            ...current,
            auditIntegrity: { ...current.auditIntegrity, status: 'unverified' },
            incidents: current.incidents.map((entry) => entry.id === incident.id ? { ...entry, status: 'resolved' } : entry),
          }));
          notify(`${action.label} executed by API; audit verification needs a refresh`);
        }
      })
      .catch(() => notify('Execution failed safely; the approved action was not applied.'))
      .finally(() => setActionBusy(null));
  };

  const handleStagePointer = (event: React.PointerEvent<HTMLElement>) => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || event.pointerType === 'touch') return;
    const rect = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty('--pointer-x', `${((event.clientX - rect.left) / rect.width - 0.5) * 18}px`);
    event.currentTarget.style.setProperty('--pointer-y', `${((event.clientY - rect.top) / rect.height - 0.5) * 14}px`);
  };

  const content = useMemo<ReactNode>(() => {
    if (view === 'overview') return <Overview data={data} source={source} onNavigate={navigate} onPointerMove={handleStagePointer} />;
    if (view === 'reviews') return <ReviewView data={data} selectedId={selectedReviewId} busyId={reviewBusyId} onSelect={setSelectedReviewId} onDecision={handleReviewDecision} />;
    if (view === 'incidents') return <IncidentsView data={data} selectedActionId={selectedActionId} approvalChecked={approvalChecked} onSelectAction={(id) => { setSelectedActionId(id); setApprovalChecked(false); }} onApprovalCheck={setApprovalChecked} onApprove={handleApprove} onExecute={handleExecute} actionBusy={actionBusy} />;
    return <AuditView data={data} />;
  // Render functions intentionally capture current operational state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, data, source, selectedReviewId, selectedActionId, approvalChecked, reviewBusyId, actionBusy]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <Sidebar view={view} open={navOpen} dark={dark} source={source} onNavigate={navigate} onClose={() => setNavOpen(false)} onTheme={() => setDark((value) => !value)} />
      <div className="app-main">
        <Topbar view={view} data={data} source={source} onMenu={() => setNavOpen(true)} />
        <main id="main-content" tabIndex={-1}>{content}</main>
      </div>
      {toast && <div className="toast" role="status"><StatusDot tone="good" /><span>{toast}</span><button onClick={() => setToast(null)} aria-label="Dismiss notification">×</button></div>}
    </div>
  );
}

export default App;
