export type View = 'overview' | 'reviews' | 'incidents' | 'audit';
export type DataSource = 'live' | 'demo' | 'connecting';
export type ConfidenceBand = 'high' | 'medium' | 'low';
export type ReviewDecision = 'match' | 'no_match' | 'skipped' | 'pending';
export type IncidentStatus = 'investigating' | 'awaiting_approval' | 'approved' | 'resolved';
export type Severity = 'critical' | 'high' | 'medium' | 'low';

export interface Metric {
  label: string;
  value: string;
  detail: string;
  delta?: string;
  trend?: 'up' | 'down' | 'flat';
  tone?: 'neutral' | 'good' | 'warning';
}

export interface ChartPoint {
  time: string;
  throughput: number;
  precision: number;
  calibration: number;
}

export interface ProductField {
  label: string;
  listing: string;
  candidate: string;
  status: 'match' | 'conflict' | 'missing';
}

export interface EvidenceSignal {
  label: string;
  value: string;
  score: number;
  tone: 'positive' | 'negative' | 'neutral';
}

export interface ReviewItem {
  id: string;
  listingId: string;
  seller: string;
  marketplace: string;
  listingTitle: string;
  canonicalId: string;
  canonicalTitle: string;
  confidence: number;
  band: ConfidenceBand;
  ageMinutes: number;
  decision: ReviewDecision;
  reason: string;
  fields: ProductField[];
  signals: EvidenceSignal[];
}

export interface ProposedAction {
  id: string;
  type: 'rollback' | 'threshold' | 'review_batch';
  label: string;
  description: string;
  impact: string;
  reversible: boolean;
  selected?: boolean;
}

export interface Incident {
  id: string;
  investigationId?: string;
  title: string;
  severity: Severity;
  status: IncidentStatus;
  startedAt: string;
  owner: string;
  metric: string;
  currentValue: string;
  baselineValue: string;
  affectedRecords: number;
  summary: string;
  findings: string[];
  proposedActions: ProposedAction[];
}

export interface AuditEvent {
  id: string;
  timestamp: string;
  actor: string;
  actorType: 'human' | 'agent' | 'system';
  action: string;
  target: string;
  detail: string;
  outcome: 'success' | 'pending' | 'blocked';
  hash: string;
}

export interface DashboardData {
  modelVersion: string;
  datasetLabel: string;
  lastUpdated: string;
  pipeline: {
    recallAtK: string;
    precision: string;
    reviewRate: string;
    decisionCoverage: string;
  };
  auditIntegrity: {
    status: 'verified' | 'invalid' | 'unverified';
    checkedEvents: number;
    headHash?: string;
  };
  metrics: Metric[];
  chart: ChartPoint[];
  reviews: ReviewItem[];
  incidents: Incident[];
  audit: AuditEvent[];
}
