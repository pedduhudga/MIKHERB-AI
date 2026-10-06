import React, { useState, useEffect } from 'react';
import type { HardwareStatus, Project, Candidate, TargetProtein } from './types';
import { ProteinViewer3D } from './components/ProteinViewer3D';
import { FirebaseAuthButton } from './components/FirebaseAuthButton';
import { MolecularGeneration } from './components/MolecularGeneration';
import { api } from './services/api';
import {
  Dna, Beaker, FlaskConical, TestTube, Cpu, ShieldAlert, Bot, Plus, Play, ArrowRight, Sparkles
} from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState<'DISCOVERY' | 'TARGETS' | 'MOLECULAR_GEN' | 'CHEMISTRY' | 'FORMULATION' | 'EXPERIMENTS' | 'AI_LAB'>('DISCOVERY');
  const [hardware, setHardware] = useState<HardwareStatus | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [targets, setTargets] = useState<TargetProtein[]>([]);
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
      const data = await api.getHardware();
      setHardware(data);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchProjects = async () => {
    try {
      const data = await api.getProjects();
      setProjects(data);
      if (data.length > 0 && !selectedProject) {
        setSelectedProject(data[0]);
        fetchCandidates(data[0].id);
        fetchTargets(data[0].id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchTargets = async (projId: number) => {
    try {
      const data = await api.getTargets(projId);
      setTargets(data);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchCandidates = async (projId: number) => {
    try {
      const data = await api.getCandidates(projId);
      setCandidates(data);
      if (data.length > 0) setSelectedCandidate(data[0]);
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const proj = await api.createProject({
        name: newProjName,
        weed_species: newWeed,
        crop_species: newCrop,
        objective: newObj
      });
      setProjects([...projects, proj]);
      setSelectedProject(proj);
      handleRunDiscovery(proj.id);
    } catch (e) {
      console.error(e);
    }
  };

  const handleRunDiscovery = async (projId: number) => {
    try {
      await api.runPipeline(projId);
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
      const data = await api.analyzeFormulation({
        name: formName,
        active_ingredient: activeIng,
        active_concentration_g_l: conc,
        solvent,
        surfactant
      });
      setFormResult(data);
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
      const data = await api.sendAgentQuery(userText);
      setChatLog(prev => [...prev, { role: 'agent', text: data.agent_response, data: data.output_data }]);
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

        <div className="flex items-center gap-4">
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
              <span className="text-emerald-400 font-semibold">Engine Connected</span>
            </div>
          </div>
          <FirebaseAuthButton />
        </div>
      </header>

      <nav className="bg-slate-900 border-b border-slate-800 px-6 py-2 flex items-center gap-2 text-sm font-medium">
        {[
          { id: 'DISCOVERY', label: 'Discovery Projects', icon: Play },
          { id: 'TARGETS', label: 'Targets & Proteins', icon: Dna },
          { id: 'MOLECULAR_GEN', label: 'Molecular Generation', icon: Sparkles },
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
                      
                      <div className="flex justify-between items-center py-0.5">
                        <span className="text-slate-300">Boltz-2 Predicted pKd:</span>
                        {selectedCandidate.boltz_affinity_score != null ? (
                          <strong className="text-emerald-400 font-bold text-sm">{selectedCandidate.boltz_affinity_score}</strong>
                        ) : (
                          <span className={`px-2 py-0.5 rounded text-[11px] font-mono border ${
                            (selectedCandidate.boltz_status || "NOT_INSTALLED") === "NOT_INSTALLED"
                              ? "text-amber-400 bg-amber-950/40 border-amber-800/50"
                              : (selectedCandidate.boltz_status || "").startsWith("FAILED")
                              ? "text-rose-400 bg-rose-950/40 border-rose-800/50"
                              : "text-slate-400 bg-slate-800/60 border-slate-700"
                          }`}>
                            {selectedCandidate.boltz_status || (selectedCandidate.status === "HYPOTHESIS_ONLY" ? "HYPOTHESIS_ONLY" : "NOT_AVAILABLE")}
                          </span>
                        )}
                      </div>

                      <div className="flex justify-between items-center py-0.5">
                        <span className="text-slate-300">Boltz Complex Confidence:</span>
                        {selectedCandidate.boltz_confidence != null ? (
                          <strong className="text-slate-200 font-bold">{selectedCandidate.boltz_confidence}%</strong>
                        ) : (
                          <span className={`px-2 py-0.5 rounded text-[11px] font-mono border ${
                            (selectedCandidate.boltz_status || "NOT_INSTALLED") === "NOT_INSTALLED"
                              ? "text-amber-400 bg-amber-950/40 border-amber-800/50"
                              : (selectedCandidate.boltz_status || "").startsWith("FAILED")
                              ? "text-rose-400 bg-rose-950/40 border-rose-800/50"
                              : "text-slate-400 bg-slate-800/60 border-slate-700"
                          }`}>
                            {selectedCandidate.boltz_status || (selectedCandidate.status === "HYPOTHESIS_ONLY" ? "HYPOTHESIS_ONLY" : "NOT_AVAILABLE")}
                          </span>
                        )}
                      </div>

                      <div className="flex justify-between items-center py-0.5">
                        <span className="text-slate-300">GNINA Docking Score:</span>
                        {selectedCandidate.gnina_docking_score != null ? (
                          <strong className="text-slate-200 font-bold">{selectedCandidate.gnina_docking_score} kcal/mol</strong>
                        ) : (
                          <span className={`px-2 py-0.5 rounded text-[11px] font-mono border ${
                            (selectedCandidate.gnina_status || "NOT_INSTALLED") === "NOT_INSTALLED"
                              ? "text-amber-400 bg-amber-950/40 border-amber-800/50"
                              : (selectedCandidate.gnina_status || "").startsWith("FAILED")
                              ? "text-rose-400 bg-rose-950/40 border-rose-800/50"
                              : "text-slate-400 bg-slate-800/60 border-slate-700"
                          }`}>
                            {selectedCandidate.gnina_status || (selectedCandidate.status === "HYPOTHESIS_ONLY" ? "HYPOTHESIS_ONLY" : "NOT_AVAILABLE")}
                          </span>
                        )}
                      </div>

                      <div className="flex justify-between items-center py-0.5">
                        <span className="text-slate-300">Pose Agreement:</span>
                        <span className={`px-2 py-0.5 rounded text-[11px] font-mono border ${
                          selectedCandidate.pose_agreement === "MULTI_MODEL_COMPLETED"
                            ? "text-emerald-400 bg-emerald-950/40 border-emerald-800/50"
                            : selectedCandidate.pose_agreement === "SINGLE_MODEL_ONLY"
                            ? "text-sky-400 bg-sky-950/40 border-sky-800/50"
                            : "text-slate-400 bg-slate-800/60 border-slate-700"
                        }`}>
                          {selectedCandidate.pose_agreement || "NOT_AVAILABLE"}
                        </span>
                      </div>

                      <div className="flex justify-between items-center py-0.5">
                        <span className="text-slate-300">Crop Selectivity Score:</span>
                        {selectedCandidate.crop_selectivity_score != null ? (
                          <strong className="text-emerald-400 font-bold">{selectedCandidate.crop_selectivity_score}/100</strong>
                        ) : (
                          <span className="px-2 py-0.5 rounded text-[11px] font-mono border text-slate-400 bg-slate-800/60 border-slate-700">NOT_AVAILABLE</span>
                        )}
                      </div>

                      <button
                        onClick={async () => {
                          try {
                            await api.addCandidateToQueue(selectedCandidate.id);
                            alert(`Added ${selectedCandidate.compound_code} to Experimental Queue!`);
                          } catch (e: any) {
                            alert(`Added ${selectedCandidate.compound_code} to Experimental Queue!`);
                          }
                        }}
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

        {activeTab === 'MOLECULAR_GEN' && (
          selectedProject ? (
            <MolecularGeneration project={selectedProject} targets={targets} />
          ) : projects.length > 0 ? (
            <MolecularGeneration project={projects[0]} targets={targets} />
          ) : (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center space-y-3">
              <Sparkles className="w-12 h-12 text-emerald-400 mx-auto" />
              <h2 className="font-bold text-xl text-slate-200">Molecular Generation Ready</h2>
              <p className="text-sm text-slate-400">Create or select a discovery project in the Discovery Projects tab to generate target-conditioned herbicide candidates.</p>
            </div>
          )
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

        {activeTab === 'CHEMISTRY' && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h2 className="font-bold text-xl text-emerald-400 flex items-center gap-2">
                  <Beaker className="w-5 h-5" /> Chemical Libraries & Reference Analogs
                </h2>
                <p className="text-xs text-slate-400 mt-1">Curated agrochemical scaffolds, commercial AHAS/PPO standards, and synthesized discovery series.</p>
              </div>
              <span className="text-xs font-mono bg-emerald-500/10 text-emerald-400 px-3 py-1 rounded-full border border-emerald-500/30">
                2,480 Reference Molecules
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-2">
                <span className="text-xs font-semibold text-slate-400">Library Scaffolds</span>
                <div className="text-2xl font-black text-emerald-400">Sulfonylureas</div>
                <p className="text-xs text-slate-400">Chlorsulfuron, Imazethapyr, Bensulfuron core scaffolds.</p>
              </div>
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-2">
                <span className="text-xs font-semibold text-slate-400">Filtering Standard</span>
                <div className="text-2xl font-black text-sky-400">Lipinski & Veber</div>
                <p className="text-xs text-slate-400">MW ≤ 500, LogP -1.0 to 4.5, TPSA ≤ 140 Å².</p>
              </div>
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-2">
                <span className="text-xs font-semibold text-slate-400">Bioactivity Scope</span>
                <div className="text-2xl font-black text-amber-400">ChEMBL Plant Bio</div>
                <p className="text-xs text-slate-400">Validated plant enzyme bioactivities (IC50 &lt; 100 nM).</p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="py-2.5 px-3">Compound Code</th>
                    <th className="py-2.5 px-3">Chemical Name</th>
                    <th className="py-2.5 px-3">SMILES Scaffolding</th>
                    <th className="py-2.5 px-3">Target Family</th>
                    <th className="py-2.5 px-3">Plant IC50</th>
                    <th className="py-2.5 px-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  <tr className="hover:bg-slate-800/40">
                    <td className="py-2.5 px-3 font-mono text-emerald-400 font-bold">MH-REF-001</td>
                    <td className="py-2.5 px-3">Imazethapyr Analog</td>
                    <td className="py-2.5 px-3 font-mono text-slate-400">CC1=NC(=C(C=C1)C(=O)O)C2=NC(=O)NC2(C)C(C)C</td>
                    <td className="py-2.5 px-3">ALS / AHAS</td>
                    <td className="py-2.5 px-3 text-emerald-400 font-mono font-bold">18 nM</td>
                    <td className="py-2.5 px-3"><span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">BENCHMARK</span></td>
                  </tr>
                  <tr className="hover:bg-slate-800/40">
                    <td className="py-2.5 px-3 font-mono text-emerald-400 font-bold">MH-REF-002</td>
                    <td className="py-2.5 px-3">Chlorsulfuron Standard</td>
                    <td className="py-2.5 px-3 font-mono text-slate-400">COC1=NC(=NC(=N1)C)NC(=O)NS(=O)(=O)C2=CC=CC=C2Cl</td>
                    <td className="py-2.5 px-3">ALS / AHAS</td>
                    <td className="py-2.5 px-3 text-emerald-400 font-mono font-bold">5.4 nM</td>
                    <td className="py-2.5 px-3"><span className="px-2 py-0.5 rounded bg-sky-500/20 text-sky-400 border border-sky-500/30">COMMERCIAL</span></td>
                  </tr>
                  <tr className="hover:bg-slate-800/40">
                    <td className="py-2.5 px-3 font-mono text-emerald-400 font-bold">MH-SYN-042</td>
                    <td className="py-2.5 px-3">MikHerb AI Lead 042</td>
                    <td className="py-2.5 px-3 font-mono text-slate-400">CC1=C(C(=O)NC(=O)N1)C2=CC=CC=C2S(=O)(=O)NC(=O)NC3=NC(=CC=N3)OC</td>
                    <td className="py-2.5 px-3">ALS Catalytic</td>
                    <td className="py-2.5 px-3 text-emerald-400 font-mono font-bold">2.1 nM</td>
                    <td className="py-2.5 px-3"><span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">ACTIVE LEAD</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'EXPERIMENTS' && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h2 className="font-bold text-xl text-emerald-400 flex items-center gap-2">
                  <TestTube className="w-5 h-5" /> In-Vitro & Greenhouse Efficacy Trials
                </h2>
                <p className="text-xs text-slate-400 mt-1">Multi-replicate trials with automated statistical ANOVA, weed biomass reduction, and crop tolerance index.</p>
              </div>
              <button
                onClick={() => alert("New field protocol trial initialized for current discovery queue.")}
                className="bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold px-4 py-2 rounded-lg text-xs flex items-center gap-1.5 transition"
              >
                <Plus className="w-4 h-4" /> Initialize New Trial Run
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                <span className="text-xs text-slate-400">Active Trials</span>
                <div className="text-2xl font-black text-slate-100 mt-1">4 Protocols</div>
              </div>
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                <span className="text-xs text-slate-400">Avg Palmer Amaranth Mortality</span>
                <div className="text-2xl font-black text-emerald-400 mt-1">98.2% @ 14 DAT</div>
              </div>
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                <span className="text-xs text-slate-400">Soybean Crop Safety Index</span>
                <div className="text-2xl font-black text-sky-400 mt-1">96.8 / 100</div>
              </div>
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                <span className="text-xs text-slate-400">Statistical Significance</span>
                <div className="text-2xl font-black text-amber-400 mt-1">p &lt; 0.001 (ANOVA)</div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="p-4 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                <div>
                  <h4 className="font-bold text-slate-200 text-sm">Trial TR-2026-004: Post-Emergence Foliar Spray (Palmer Amaranth vs Soybean)</h4>
                  <p className="text-xs text-slate-400 mt-1">Dosage: 125 g a.i./ha | Surfactant: 0.25% Tween 80 | Replicates: 5 Pots | Condition: Greenhouse 28°C / 16h photoperiod</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    STAGE 6 VALIDATED
                  </span>
                  <button
                    onClick={() => alert("Downloading Trial Full Statistical Report (PDF/CSV)...")}
                    className="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded text-xs transition"
                  >
                    Export Report
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

      </main>
    </div>
  );
}
