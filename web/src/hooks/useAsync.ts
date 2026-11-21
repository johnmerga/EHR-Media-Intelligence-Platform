import { useEffect, useState } from "react";

export type AsyncState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; message: string };

/**
 * Runs `task` whenever `key` changes and tracks its state. A `null` key means
 * "nothing to load". When the key changes mid-flight, the previous request is
 * aborted so a slow response can never overwrite a newer one.
 */
export function useAsync<T>(
  key: string | null,
  task: (signal: AbortSignal) => Promise<T>,
  retryToken = 0,
): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: "idle" });

  useEffect(() => {
    if (key === null) {
      setState({ status: "idle" });
      return;
    }
    const controller = new AbortController();
    setState({ status: "loading" });
    task(controller.signal)
      .then((data) => setState({ status: "success", data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof Error && error.name === "ApiError"
            ? error.message
            : "Could not reach the server. Check your connection and try again.";
        setState({ status: "error", message });
      });
    return () => controller.abort();
    // `task` is intentionally not a dependency: `key` identifies the request.
  }, [key, retryToken]);

  return state;
}
