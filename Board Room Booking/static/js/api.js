const activeControllers = {};

export async function fetchWithAbort(url, options = {}, key) {
  if (activeControllers[key]) {
    activeControllers[key].abort();
  }
  
  const controller = new AbortController();
  activeControllers[key] = controller;
  
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    const data = await res.json();
    delete activeControllers[key];
    return data;
  } catch (err) {
    if (err.name === 'AbortError') return { aborted: true };
    delete activeControllers[key];
    throw err;
  }
}
