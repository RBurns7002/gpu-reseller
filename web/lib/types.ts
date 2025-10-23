export type Region = {
  code: string;
  status: string;
  total_gpus: number;
  free_gpus: number;
  utilization: number;
};

export type SimulationRegionPoint = {
  code: string;
  timestamp: string;
  utilization: number; // percentage 0-100
  revenue_cents: number;
  cost_cents: number;
  profit_cents: number;
  total_gpus: number;
};

export type SimulationTotals = {
  revenue_cents: number;
  cost_cents: number;
  profit_cents: number;
  avg_utilization: number; // percentage 0-100
};

export type SimulationHistoryPoint = {
  timestamp: string;
  totals: SimulationTotals;
  regions: SimulationRegionPoint[];
};

export type SimulationStreamPayload = SimulationHistoryPoint & {
  iteration: number;
  step_hours: number;
};
