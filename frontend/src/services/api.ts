import { auth } from './firebase';

// API Base URL configured via environment variables for Vercel deployment
const API_BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

const getAuthHeaders = async (includeContentType: boolean = true): Promise<Record<string, string>> => {
  const headers: Record<string, string> = {};
  if (includeContentType) {
    headers['Content-Type'] = 'application/json';
  }
  try {
    if (auth?.currentUser) {
      const token = await auth.currentUser.getIdToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }
  } catch (e) {
    console.warn("Could not retrieve Firebase Auth token:", e);
  }
  return headers;
};

export const api = {
  getHardware: async () => {
    const res = await fetch(`${API_BASE_URL}/api/v1/system/hardware`);
    if (!res.ok) throw new Error(`Hardware fetch failed with status ${res.status}`);
    return res.json();
  },

  getEngines: async () => {
    const res = await fetch(`${API_BASE_URL}/api/v1/system/engines`);
    if (!res.ok) throw new Error(`Engines fetch failed with status ${res.status}`);
    return res.json();
  },

  getProjects: async () => {
    const res = await fetch(`${API_BASE_URL}/api/v1/projects`);
    if (!res.ok) throw new Error(`Projects fetch failed with status ${res.status}`);
    return res.json();
  },

  createProject: async (project: { name: string; weed_species: string; crop_species: string; objective: string }) => {
    const headers = await getAuthHeaders(true);
    const res = await fetch(`${API_BASE_URL}/api/v1/projects`, {
      method: 'POST',
      headers,
      body: JSON.stringify(project)
    });
    if (!res.ok) throw new Error(`Create project failed with status ${res.status}`);
    return res.json();
  },

  runPipeline: async (projectId: number) => {
    const headers = await getAuthHeaders(false);
    const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/run`, {
      method: 'POST',
      headers
    });
    if (!res.ok) throw new Error(`Run pipeline failed with status ${res.status}`);
    return res.json();
  },

  getTargets: async (projectId: number) => {
    const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/targets`);
    if (!res.ok) throw new Error(`Targets fetch failed with status ${res.status}`);
    return res.json();
  },

  getCandidates: async (projectId: number) => {
    const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/candidates`);
    if (!res.ok) throw new Error(`Candidates fetch failed with status ${res.status}`);
    return res.json();
  },

  addCandidateToQueue: async (candidateId: number) => {
    const headers = await getAuthHeaders(false);
    const res = await fetch(`${API_BASE_URL}/api/v1/candidates/${candidateId}/add_to_queue`, {
      method: 'POST',
      headers
    });
    if (!res.ok) throw new Error(`Add to queue failed with status ${res.status}`);
    return res.json();
  },

  analyzeFormulation: async (formulation: {
    name: string;
    active_ingredient: string;
    active_concentration_g_l: number;
    solvent: string;
    surfactant: string;
  }) => {
    const headers = await getAuthHeaders(true);
    const res = await fetch(`${API_BASE_URL}/api/v1/formulation/analyze`, {
      method: 'POST',
      headers,
      body: JSON.stringify(formulation)
    });
    if (!res.ok) throw new Error(`Formulation analysis failed with status ${res.status}`);
    return res.json();
  },

  sendAgentQuery: async (query: string) => {
    const headers = await getAuthHeaders(false);
    const res = await fetch(`${API_BASE_URL}/api/v1/agent/chat?query=${encodeURIComponent(query)}`, {
      method: 'POST',
      headers
    });
    if (!res.ok) throw new Error(`Agent query failed with status ${res.status}`);
    return res.json();
  }
};

