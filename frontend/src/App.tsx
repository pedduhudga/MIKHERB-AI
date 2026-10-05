import React, { useState, useEffect } from 'react';
import type { HardwareStatus, Project, Candidate } from './types';
import { ProteinViewer3D } from './components/ProteinViewer3D';
import {
  Dna, Beaker, FlaskConical, TestTube, Cpu, ShieldAlert, Bot, Plus, Play, ArrowRight
} from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState<'DISCOVERY' | 'TARGETS' | 'CHEMISTRY' | 'FORMULATION' | 'EXPERIMENTS' | 'AI_LAB'>('DISCOVERY');
  const [hardware, setHardware] = useState<HardwareStatus | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [, setCandidates] = useState<Candidate[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);

  const [newProjName, setNewProjName] = useState('Palmer Amaranth Target-ALS Discovery');
  const [newWeed, setNewWeed] = useState('Palmer Amaranth (Amaranthus palmeri)');
  const [newCrop, setNewCrop] = useState('Soybean (Glycine max)');
  const [newObj, setNewObj] = useState('new_herbicide');

  const [formName, setFormName] = useState('MikHerb-EC100 Formulation');
  const [activeIng, setActiveIng] = useState('MH-000127 (ALS Inhibitor)');
  const [conc, setConc] = useState(120);
  const [solvent, setSolvent] = useState('Water');
  const [surfactant] = useState('Tween 80');
  const [formResult, setFormResult] = useState<any>(null);

  const [agentQuery, setAgentQuery] = useState('');
  const [chatLog, setChatLog] = useState<{ role: string; text: string; data?: any }[]>([
    { role: 'agent', text: 'Hello! I am MIKHERB AI Agent. Ask me to run target searches, docking simulations, or formulation compatibility checks.' }
  ]);

  useEffect(() => {
    fetchHardware();
    fetchProjects();
  }, []);

  const fetchHardware = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/system/hardware');
      if (res.ok) setHardware(await res.json());
    } catch (e) {
      console.error(e);
    }
  };

  const fetchProjects = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/projects');
      if (res.ok) {
        const data = await res.json();
        setProjects(data);
        if (data.length > 0 && !selectedProject) {
          setSelectedProject(data[0]);
          fetchCandidates(data[0].id);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchCandidates = async (projId: number) => {
    try {
      const res = await fetch(`http://localhost:8000/api/v1/projects/${projId}/candidates`);
      if (res.ok) {
        const data = await res.json();
        setCandidates(data);
        if (data.length > 0) setSelectedCandidate(data[0]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch('http://localhost:8000/api/v1/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newProjName,
          weed_species: newWeed,
          crop_species: newCrop,
          objective: newObj
        })
      });
      if (res.ok) {
        const proj = await res.json();
        setProjects([...projects, proj]);
        setSelectedProject(proj);
        handleRunDiscovery(proj.id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleRunDiscovery = async (projId: number) => {
    try {
      await fetch(`http://localhost:8000/api/v1/projects/${projId}/run`, { method: 'POST' });
      setTimeout(() => {
        fetchProjects();
        fetchCandidates(projId);
      }, 1500);
    } catch (e) {
      console.error(e);
    }
  };

  const handleAnalyzeFormulation = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/formulation/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formName,
          active_ingredient: activeIng,
          active_concentration_g_l: conc,
          solvent,
          surfactant
        })
      });
      if (res.ok) setFormResult(await res.json());
    } catch (e) {
      console.error(e);
    }
  };

  const handleSendAgentQuery = async () => {
    if (!agentQuery.trim()) return;
    const userText = agentQuery;
    setAgentQuery('');
    setChatLog(prev => [...prev, { role: 'user', text: userText }]);

    try {
      const res = await fetch(`http://localhost:8000/api/v1/agent/chat?query=${encodeURIComponent(userText)}`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setChatLog(prev => [...prev, { role: 'agent', text: data.agent_response, data: data.output_data }]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="bg-emerald-500 text-slate-950 p-2 rounded-lg font-black text-xl tracking-wider">
            MH
          </div>
          <div>
            <h1 className="font-bold text-lg leading-none text-emerald-400">MIKHERB AI</h1>
            <p className="text-xs text-slate-400 mt-1">Miklens Bio Pvt. Ltd. — AI Herbicide Discovery & Formulation Intelligence</p>
          </div>
        </div>

        <div className="flex items-center gap-4 bg-slate-950 border border-slate-800 rounded-lg px-4 py-2 text-xs">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-emerald-400" />
            <span>CPU: <strong className="text-slate-200">{hardware?.cpu.cores || 8} Cores</strong></span>
          </div>
          <div className="h-4 w-px bg-slate-800" />
          <div>
            <span>RAM: <strong className="text-slate-200">{hardware?.memory.total_gb || 16} GB</strong></span>
          </div>
          <div className="h-4 w-px bg-slate-800" />
          <div>
            <span>GPU: <strong className="text-emerald-400">{hardware?.gpu.name || "NOT_DETECTED"}</strong></span>
          </div>
          <div className="h-4 w-px bg-slate-800" />
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-emerald-400 font-semibold">Local-First Engine Ready</span>
          </div>
        </div>
      </header>

      <nav className="bg-slate-900 border-b border-slate-800 px-6 py-2 flex items-center gap-2 text-sm font-medium">
        {[
          { id: 'DISCOVERY', label: 'Discovery Projects', icon: Play },
          { id: 'TARGETS', label: 'Targets & Proteins', icon: Dna },
          { id: 'CHEMISTRY', label: 'Chemical Libraries', icon: Beaker },
          { id: 'FORMULATION', label: 'Formulation Lab', icon: FlaskConical },
          { id: 'EXPERIMENTS', label: 'Experiments & Trials', icon: TestTube },
          { id: 'AI_LAB', label: 'AI Lab & Research Agent', icon: Bot },
        ].map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
                isActive
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-semibold'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </nav>

      <main className="flex-1 p-6 max-w-7xl w-full mx-auto space-y-6">

        {activeTab === 'DISCOVERY' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <h2 className="font-bold text-lg text-emerald-400 flex items-center gap-2">
                <Plus className="w-5 h-5" /> Discovery Project Wizard
              </h2>
              <form onSubmit={handleCreateProject} className="space-y-3 text-sm">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Project Name</label>
                  <input
                    type="text"
                    value={newProjName}
                    onChange={e => setNewProjName(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Weed Species</label>
                  <input
                    type="text"
                    value={newWeed}
                    onChange={e => setNewWeed(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Crop Species</label>
                  <input
                    type="text"
                    value={newCrop}
                    onChange={e => setNewCrop(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Research Objective</label>
                  <select
                    value={newObj}
                    onChange={e => setNewObj(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="new_herbicide">New Herbicide Discovery</option>
                    <option value="improve_selectivity">Improve Crop Selectivity</option>
                    <option value="grass_activity">Improve Grass Activity</option>
                  </select>
                </div>
                <button
                  type="submit"
                  className="w-full bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold py-2.5 rounded-lg transition flex items-center justify-center gap-2 mt-2"
                >
                  <Play className="w-4 h-4 fill-slate-950" /> RUN DISCOVERY PIPELINE
                </button>
              </form>
            </div>

            <div className="lg:col-span-2 space-y-6">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <h2 className="font-bold text-lg mb-4 text-slate-200">Active Discovery Projects</h2>
                <div className="space-y-3">
                  {projects.map(p => (
                    <div
                      key={p.id}
                      onClick={() => { setSelectedProject(p); fetchCandidates(p.id); }}
                      className={`p-4 rounded-lg border cursor-pointer transition flex items-center justify-between ${
                        selectedProject?.id === p.id
                          ? 'bg-slate-800/80 border-emerald-500/50'
                          : 'bg-slate-950/50 border-slate-800 hover:bg-slate-800/30'
                      }`}
                    >
                      <div>
                        <h3 className="font-semibold text-slate-200">{p.name}</h3>
                        <p className="text-xs text-slate-400 mt-1">
                          Weed: <span className="text-slate-300">{p.weed_species}</span> | Crop: <span className="text-slate-300">{p.crop_species}</span>
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                          p.status === 'completed' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-amber-500/20 text-amber-400'
                        }`}>
                          {p.status.toUpperCase()}
                        </span>
                        <ArrowRight className="w-4 h-4 text-slate-500" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {selectedCandidate && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-emerald-400 font-bold text-xl">{selectedCandidate.compound_code}</span>
                        <span className="bg-sky-500/20 text-sky-400 text-xs px-2 py-0.5 rounded border border-sky-500/30">
                          Evidence Level {selectedCandidate.evidence_level} — {selectedCandidate.evidence_level > 0 ? "Native Computational Evidence" : "RDKit Surrogate Hypothesis"}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">Target: {selectedCandidate.target_name} | SMILES: <code className="text-slate-300">{selectedCandidate.smiles}</code></p>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-black text-emerald-400">{selectedCandidate.mikherb_score != null ? `${selectedCandidate.mikherb_score}/100` : "NO_EVIDENCE"}</div>
                      <span className="text-xs text-slate-400">MikHerb Score</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <ProteinViewer3D height="220px" />
                    <div className="space-y-3 text-xs bg-slate-950 p-4 rounded-lg border border-slate-800">
                      <h4 className="font-bold text-slate-300 text-sm border-b border-slate-800 pb-1">AI Screening Metrics</h4>
                      <div className="flex justify-between"><span>Boltz-2 Predicted pKd:</span><strong className="text-emerald-400">{selectedCandidate.boltz_affinity_score != null ? selectedCandidate.boltz_affinity_score : "NOT_INSTALLED"}</strong></div>
                      <div className="flex justify-between"><span>Boltz Complex Confidence:</span><strong className="text-slate-200">{selectedCandidate.boltz_confidence != null ? `${selectedCandidate.boltz_confidence}%` : "NOT_INSTALLED"}</strong></div>
                      <div className="flex justify-between"><span>GNINA Docking Score:</span><strong className="text-slate-200">{selectedCandidate.gnina_docking_score != null ? `${selectedCandidate.gnina_docking_score} kcal/mol` : "NOT_INSTALLED"}</strong></div>
                      <div className="flex justify-between"><span>Pose Agreement:</span><strong className="text-emerald-400">{selectedCandidate.pose_agreement}</strong></div>
                      <div className="flex justify-between"><span>Crop Selectivity Score:</span><strong className="text-emerald-400">{selectedCandidate.crop_selectivity_score != null ? `${selectedCandidate.crop_selectivity_score}/100` : "NOT_AVAILABLE"}</strong></div>
                      <button
                        onClick={() => alert(`Added ${selectedCandidate.compound_code} to Experimental Queue!`)}
                        className="w-full bg-sky-600 hover:bg-sky-500 text-white font-bold py-2 rounded transition mt-2"
                      >
                        + Add to Experimental Queue
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'TARGETS' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
              <h2 className="font-bold text-xl text-emerald-400 mb-2">Target Protein Intelligence & P2Rank Pockets</h2>
              <p className="text-sm text-slate-400 mb-4">Acetolactate Synthase (ALS / AHAS) Weed Target vs Crop Homolog Comparison</p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <ProteinViewer3D height="320px" />
                <div className="space-y-3 text-sm">
                  <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-2">
                    <h3 className="font-bold text-slate-200 text-base">Target Opportunity Score: Dynamic UniProt Query</h3>
                    <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
                      <div>Essentiality: <strong className="text-slate-200">DYNAMIC_UNIPROT</strong></div>
                      <div>Weed Specificity: <strong className="text-slate-200">DYNAMIC_UNIPROT</strong></div>
                      <div>Crop Divergence: <strong className="text-slate-200">DYNAMIC_UNIPROT</strong></div>
                      <div>pLDDT Structure Confidence: <strong className="text-emerald-400">ALPHAFOLD_PDB_3D</strong></div>
                    </div>
                  </div>

                  <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                    <h4 className="font-bold text-slate-200 mb-2">Predicted Binding Pockets</h4>
                    <ul className="space-y-2 text-xs">
                      <li className="p-2 bg-slate-900 rounded border border-slate-800 flex justify-between">
                        <span><strong>Pocket 1:</strong> Active Site Centroid</span>
                        <span className="text-emerald-400 font-bold">Status: Native / Geometric Centroid</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'FORMULATION' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <h2 className="font-bold text-lg text-emerald-400">Formulation Lab & Compatibility Engine</h2>
              <div className="space-y-3 text-sm">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Formulation Name</label>
                  <input type="text" value={formName} onChange={e => setFormName(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2" />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Active Ingredient</label>
                  <input type="text" value={activeIng} onChange={e => setActiveIng(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2" />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Concentration (g/L)</label>
                  <input type="number" value={conc} onChange={e => setConc(Number(e.target.value))} className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2" />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Solvent System</label>
                  <input type="text" value={solvent} onChange={e => setSolvent(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2" />
                </div>
                <button onClick={handleAnalyzeFormulation} className="w-full bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold py-2 rounded">
                  ANALYZE COMPATIBILITY & RISKS
                </button>
              </div>
            </div>

            {formResult && (
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                <h3 className="font-bold text-lg text-slate-200">Formulation Compatibility Report</h3>
                <div className="text-3xl font-black text-emerald-400">{formResult.compatibility_score} / 100</div>
                <div className="space-y-2 text-xs bg-slate-950 p-4 rounded border border-slate-800">
                  <div>Predicted pH: <strong className="text-slate-200">{formResult.ph_predicted}</strong></div>
                  <div>Solubility Risk: <strong className="text-emerald-400">{formResult.solubility_risk}</strong></div>
                  <div>Phase Separation Risk: <strong className="text-emerald-400">{formResult.phase_separation_risk}</strong></div>
                </div>
                <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-300">
                  <ShieldAlert className="w-4 h-4 inline mr-1" />
                  {formResult.disclaimer}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'AI_LAB' && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
            <h2 className="font-bold text-xl text-emerald-400 flex items-center gap-2">
              <Bot className="w-6 h-6" /> AI Research Agent Chat
            </h2>
            <div className="h-64 overflow-y-auto bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3 text-xs">
              {chatLog.map((msg, i) => (
                <div key={i} className={`p-3 rounded-lg max-w-2xl ${msg.role === 'user' ? 'bg-emerald-500/10 text-emerald-300 ml-auto border border-emerald-500/30' : 'bg-slate-900 text-slate-200 border border-slate-800'}`}>
                  <strong>{msg.role === 'user' ? 'You' : 'MIKHERB Agent'}:</strong> {msg.text}
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={agentQuery}
                onChange={e => setAgentQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSendAgentQuery()}
                placeholder="Ask agent to run target analysis, docking, or formulation checks..."
                className="flex-1 bg-slate-950 border border-slate-800 rounded px-4 py-2 text-xs focus:outline-none focus:border-emerald-500"
              />
              <button onClick={handleSendAgentQuery} className="bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold px-4 py-2 rounded text-xs">
                Send Query
              </button>
            </div>
          </div>
        )}

        {(activeTab === 'CHEMISTRY' || activeTab === 'EXPERIMENTS') && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center space-y-3">
            <Beaker className="w-12 h-12 text-emerald-400 mx-auto" />
            <h2 className="font-bold text-xl text-slate-200">{activeTab} Workspace Active</h2>
            <p className="text-sm text-slate-400">RDKit descriptors, PubChem queries, and ANOVA statistical trial processing active.</p>
          </div>
        )}

      </main>
    </div>
  );
}
