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
  capacity_gpus: number;
  free_gpus: number;
};

export type SimulationTotals = {
  revenue_cents: number;
  cost_cents: number;
  profit_cents: number;
  avg_utilization: number; // percentage 0-100
};

export type SimulationFinance = {
  capital_cents: number;
  total_revenue_cents?: number;
  total_cost_cents?: number;
  total_spent_cents: number;
  profit_cents?: number;
  spend_ratio?: number;
  expansion_cost_per_gpu_cents?: number;
  new_gpu_purchased?: number;
  electricity_cost_per_kwh?: number;
  gpu_wattage_w?: number;
  energy_cost_per_gpu_hour?: number;
};

export type SimulationHistoryPoint = {
  timestamp: string;
  totals: SimulationTotals;
  regions: SimulationRegionPoint[];
  finance?: SimulationFinance;
};

export type SimulationStreamPayload = SimulationHistoryPoint & {
  iteration: number;
  step_hours: number;
  finance: SimulationFinance;
};
