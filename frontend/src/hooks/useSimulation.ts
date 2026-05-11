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
}

export type SimAction =
  | { type: "stage_start"; stage: string; message: string }
  | { type: "stage_complete"; stage: string; data: Record<string, unknown> }
  | { type: "track_start"; track: number; message: string }
  | { type: "round_complete"; track: number; round: number; total_rounds: number }
  | { type: "track_complete"; track: number; status: string }
  | { type: "simulation_complete"; sim_id: string }
  | { type: "simulation_error"; message: string }
  | { type: "cost_update"; cost_usd: number; cap_usd: number }
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
  };
}

function simulationReducer(state: SimulationState, action: SimAction): SimulationState {
  switch (action.type) {
    case "stage_start": {
      const nextStatus = STAGE_TRANSITIONS[action.stage] ?? state.status;
      return { ...state, status: nextStatus, currentStage: action.stage };
    }
    case "stage_complete": {
      const agents = (action.data.agent_count as number) ?? state.agents;
      return { ...state, agents };
    }
    case "track_start":
      return { ...state, status: "RUNNING" };
    case "round_complete":
      return { ...state, round: action.round, totalRounds: action.total_rounds };
    case "simulation_complete":
      return { ...state, status: "REPORT", simId: action.sim_id };
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
      dispatch({ type: "sim_id_set", simId } as unknown as SimAction);

      const es = new EventSource(`/simulate/${simId}/status`);
      eventSourceRef.current = es;

      es.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          const { event: eventType, ...data } = payload;
          // The SSE format is: data: {"event": "stage_start", ...}
          // EventSource.onmessage receives the full JSON
          const evt = data.event ?? eventType;
          switch (evt) {
            case "stage_start":
              dispatch({ type: "stage_start", stage: data.stage, message: data.message });
              break;
            case "stage_complete":
              dispatch({ type: "stage_complete", stage: data.stage, data: data });
              break;
            case "track_start":
              dispatch({ type: "track_start", track: data.track, message: data.message });
              break;
            case "round_complete":
              dispatch({ type: "round_complete", track: data.track, round: data.round, total_rounds: data.total_rounds ?? 10 });
              break;
            case "track_complete":
              dispatch({ type: "track_complete", track: data.track, status: data.status });
              break;
            case "simulation_complete":
              dispatch({ type: "simulation_complete", sim_id: data.sim_id ?? simId });
              closeConnection();
              break;
            case "cost_update":
              dispatch({ type: "cost_update", cost_usd: data.cost_usd, cap_usd: data.cap_usd });
              break;
          }
        } catch {
          // ignore unparseable events
        }
      };

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
