/** `process` for the browser bundle: no environment, the root as the working directory. */
export const process = { env: {} as Record<string, string | undefined>, cwd: () => "/", platform: "browser" };
