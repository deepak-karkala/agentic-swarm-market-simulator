import { useReducer, useCallback, useRef, useEffect } from "react";

// ── State types ──

export type SimStatus =
  | "INPUT"
  | "STAGE0"
  | "STAGE1"
  | "STAGE2"
  | "RUNNING"
  | "PAUSED"
  | "REPORT"
  | "ERROR";

export interface SimulationState {
  status: SimStatus;
  simId: string | null;
  round: number;
  totalRounds: number;
  costUsd: number;
  currentStage: string;
  errorMessage: string;
  agents: number;
  reportSections: Record<string, string> | null;
}

export type SimAction =
  | { type: "sim_id_set"; simId: string }
  | { type: "stage_start"; stage: string; message: string }
  | { type: "stage_complete"; stage: string; data: Record<string, unknown> }
  | { type: "track_start"; track: number; message: string }
  | { type: "round_complete"; track: number; round: number; total_rounds: number }
  | { type: "track_complete"; track: number; status: string }
  | { type: "simulation_complete"; sim_id: string }
  | { type: "simulation_error"; message: string }
  | { type: "cost_update"; cost_usd: number; cap_usd: number }
  | { type: "report_loaded"; sections: Record<string, string> }
  | { type: "reset" };

const STAGE_TRANSITIONS: Record<string, SimStatus> = {
  stage0: "STAGE0",
  stage1: "STAGE1",
  stage2: "STAGE2",
  stage3: "RUNNING",
};

function makeInitialState(): SimulationState {
  return {
    status: "INPUT",
    simId: null,
    round: 0,
    totalRounds: 10,
    costUsd: 0,
    currentStage: "",
    errorMessage: "",
    agents: 0,
    reportSections: null,
  };
}

function simulationReducer(state: SimulationState, action: SimAction): SimulationState {
  switch (action.type) {
    case "sim_id_set":
      return { ...state, simId: action.simId };
    case "stage_start": {
      const nextStatus = STAGE_TRANSITIONS[action.stage] ?? state.status;
      return { ...state, status: nextStatus, currentStage: action.stage };
    }
    case "stage_complete": {
      const data = action.data;
      const agents = (data.agent_count as number) ?? state.agents;
      return { ...state, agents };
    }
    case "track_start":
      return { ...state, status: "RUNNING" };
    case "round_complete":
      return { ...state, round: action.round, totalRounds: action.total_rounds };
    case "simulation_complete":
      return { ...state, status: "REPORT", simId: action.sim_id };
    case "report_loaded":
      return { ...state, reportSections: action.sections };
    case "simulation_error":
      return { ...state, status: "ERROR", errorMessage: action.message };
    case "cost_update":
      return { ...state, costUsd: action.cost_usd };
    case "reset":
      return makeInitialState();
    default:
      return state;
  }
}

// ── Hook ──

export function useSimulation() {
  const [state, dispatch] = useReducer(simulationReducer, undefined, makeInitialState);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttempts = useRef(0);

  const closeConnection = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    reconnectAttempts.current = 0;
  }, []);

  const startSimulation = useCallback(
    (simId: string) => {
      closeConnection();
      dispatch({ type: "reset" });
      dispatch({ type: "sim_id_set", simId });

      const es = new EventSource(`/simulate/${simId}/status`);
      eventSourceRef.current = es;

      // Named SSE events — the backend emits `event: stage_start`,
      // `event: stage_complete`, etc. onmessage fires for default
      // unnamed events, but these are named.
      const addEvt = (name: string, handler: (data: Record<string, unknown>) => void) => {
        es.addEventListener(name, (e: Event) => {
          try {
            const msg = e as MessageEvent;
            const parsed: unknown = JSON.parse(msg.data);
            if (typeof parsed === "object" && parsed !== null) {
              handler(parsed as Record<string, unknown>);
            }
          } catch {
            // ignore unparseable
          }
        });
      };

      addEvt("stage_start", (data) => {
        dispatch({ type: "stage_start", stage: String(data.stage ?? ""), message: String(data.message ?? "") });
      });
      addEvt("stage_complete", (data) => {
        dispatch({ type: "stage_complete", stage: String(data.stage ?? ""), data });
      });
      addEvt("track_start", (data) => {
        dispatch({ type: "track_start", track: Number(data.track ?? 0), message: String(data.message ?? "") });
      });
      addEvt("round_complete", (data) => {
        dispatch({ type: "round_complete", track: Number(data.track ?? 0), round: Number(data.round ?? 0), total_rounds: Number(data.total_rounds ?? 10) });
      });
      addEvt("track_complete", (data) => {
        dispatch({ type: "track_complete", track: Number(data.track ?? 0), status: String(data.status ?? "") });
      });
      addEvt("simulation_complete", (data) => {
        const completedSimId = String(data.sim_id ?? simId);
        dispatch({ type: "simulation_complete", sim_id: completedSimId });
        closeConnection();
      });
      addEvt("cost_update", (data) => {
        dispatch({ type: "cost_update", cost_usd: Number(data.cost_usd ?? 0), cap_usd: Number(data.cap_usd ?? 10) });
      });

      es.onerror = () => {
        if (reconnectAttempts.current < 3) {
          reconnectAttempts.current += 1;
        } else {
          dispatch({ type: "simulation_error", message: "SSE connection lost — simulation may still be running." });
          closeConnection();
        }
      };
    },
    [closeConnection],
  );

  useEffect(() => {
    return () => closeConnection();
  }, [closeConnection]);

  return { state, dispatch, startSimulation };
}
