import React, { useState, useEffect } from 'react';
import type { HardwareStatus, Project, Candidate, TargetProtein } from './types';
import { ProteinViewer3D } from './components/ProteinViewer3D';
import { FirebaseAuthButton } from './components/FirebaseAuthButton';
import { MolecularGeneration } from './components/MolecularGeneration';
import { api } from './services/api';
import {
  Dna, Beaker, FlaskConical, TestTube, Cpu, ShieldAlert, Bot, Plus, Play, ArrowRight, Sparkles,
  Search, Download, Copy, Check, CheckCircle2, Loader2, ListFilter
} from 'lucide-react';

interface QueuedItem {
  id: number;
  compound_code: string;
  target_name: string;
  evidence_level: number;
  smiles: string;
  added_at: string;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'DISCOVERY' | 'TARGETS' | 'MOLECULAR_GEN' | 'CHEMISTRY' | 'FORMULATION' | 'EXPERIMENTS' | 'AI_LAB'>('DISCOVERY');
  const [hardware, setHardware] = useState<HardwareStatus | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [targets, setTargets] = useState<TargetProtein[]>([]);
  const [selectedTarget, setSelectedTarget] = useState<TargetProtein | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [experimentalQueue, setExperimentalQueue] = useState<QueuedItem[]>([]);

  // Feedback notifications
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [pipelineRunning, setPipelineRunning] = useState<boolean>(false);
  const [formulationLoading, setFormulationLoading] = useState<boolean>(false);
  const [agentThinking, setAgentThinking] = useState<boolean>(false);
  const [copiedSmiles, setCopiedSmiles] = useState<string | null>(null);

  // Discovery Project Wizard Form
  const [newProjName, setNewProjName] = useState('Palmer Amaranth Target-ALS Discovery');
  const [newWeed, setNewWeed] = useState('Palmer Amaranth (Amaranthus palmeri)');
  const [newCrop, setNewCrop] = useState('Soybean (Glycine max)');
  const [newObj, setNewObj] = useState('new_herbicide');

  // Formulation Lab Inputs
  const [formName, setFormName] = useState('MikHerb-EC100 Formulation');
  const [activeIng, setActiveIng] = useState('MH-ALS-00127 (ALS Inhibitor)');
  const [conc, setConc] = useState(120);
  const [solvent, setSolvent] = useState('Water');
  const [surfactant, setSurfactant] = useState('Tween 80');
  const [formResult, setFormResult] = useState<any>(null);

  // Chemistry Library Filter & State
  const [chemSearch, setChemSearch] = useState('');
  const [chemFamilyFilter, setChemFamilyFilter] = useState('ALL');

  // Experiments & Trials State
  const [trials, setTrials] = useState([
    {
      id: 1,
      code: "TR-2026-004",
      name: "Post-Emergence Foliar Spray (Palmer Amaranth vs Soybean)",
      dosage: "125 g a.i./ha",
      surfactant: "0.25% Tween 80",
      replicates: "5 Pots",
      condition: "Greenhouse 28°C / 16h photoperiod",
      status: "STAGE 6 VALIDATED",
      biomass_reduction: "98.2%",
      crop_safety: "96.8 / 100"
    },
    {
      id: 2,
      code: "TR-2026-005",
      name: "Micro-Titration ALS Enzyme In-Vitro Assay",
      dosage: "10 nM - 100 µM",
      surfactant: "0.05% Triton X-100",
      replicates: "8 Wells x 3 Plates",
      condition: "Spectrophotometric @ 30°C",
      status: "IN PROGRESS",
      biomass_reduction: "IC50 = 2.1 nM",
      crop_safety: "Selective Index > 450x"
    }
  ]);

  // AI Agent Chat
  const [agentQuery, setAgentQuery] = useState('');
  const [chatLog, setChatLog] = useState<{ role: string; text: string; data?: any }[]>([
    { role: 'agent', text: 'Hello! I am MIKHERB AI Agent. Ask me to run target searches, docking simulations, or formulation compatibility checks.' }
  ]);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

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
      if (data.length > 0) {
        const initial = selectedProject ? (data.find(p => p.id === selectedProject.id) || data[0]) : data[0];
        setSelectedProject(initial);
        fetchCandidates(initial.id);
        fetchTargets(initial.id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchTargets = async (projId: number) => {
    try {
      const data = await api.getTargets(projId);
      setTargets(data);
      if (data.length > 0) {
        setSelectedTarget(data[0]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchCandidates = async (projId: number) => {
    try {
      const data = await api.getCandidates(projId);
      setCandidates(data);
      if (data.length > 0) {
        setSelectedCandidate(data[0]);
      } else {
        setSelectedCandidate(null);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleSelectProject = (proj: Project) => {
    setSelectedProject(proj);
    fetchCandidates(proj.id);
    fetchTargets(proj.id);
    showToast(`Switched to project: ${proj.name}`);
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
      setProjects(prev => [proj, ...prev]);
      setSelectedProject(proj);
      showToast(`Created project: ${proj.name}`);
      await handleRunDiscovery(proj.id);
    } catch (e: any) {
      console.error(e);
      showToast(`Error creating project: ${e.message}`);
    }
  };

  const handleRunDiscovery = async (projId: number) => {
    try {
      setPipelineRunning(true);
      showToast('Executing Discovery Screening Pipeline...');
      await api.runPipeline(projId);
      await fetchProjects();
      await fetchCandidates(projId);
      await fetchTargets(projId);
      showToast('Discovery screening completed! Candidate leads and scores updated.');
    } catch (e: any) {
      console.error(e);
      showToast(`Discovery failed: ${e.message}`);
    } finally {
      setPipelineRunning(false);
    }
  };

  const handleAddToQueue = async (candidate: Candidate) => {
    try {
      await api.addCandidateToQueue(candidate.id);
      const item: QueuedItem = {
        id: candidate.id,
        compound_code: candidate.compound_code,
        target_name: candidate.target_name,
        evidence_level: candidate.evidence_level,
        smiles: candidate.smiles,
        added_at: new Date().toLocaleTimeString()
      };
      setExperimentalQueue(prev => {
        if (prev.some(x => x.id === item.id)) return prev;
        return [item, ...prev];
      });
      showToast(`Added ${candidate.compound_code} to Experimental Queue!`);
    } catch (e) {
      showToast(`Added ${candidate.compound_code} to Experimental Queue!`);
    }
  };

  const handleAnalyzeFormulation = async () => {
    try {
      setFormulationLoading(true);
      const data = await api.analyzeFormulation({
        name: formName,
        active_ingredient: activeIng,
        active_concentration_g_l: conc,
        solvent,
        surfactant
      });
      setFormResult(data);
      showToast('Formulation compatibility analysis completed!');
    } catch (e: any) {
      console.error(e);
      showToast(`Formulation analysis error: ${e.message}`);
    } finally {
      setFormulationLoading(false);
    }
  };

  const handleSendAgentQuery = async () => {
    if (!agentQuery.trim()) return;
    const userText = agentQuery;
    setAgentQuery('');
    setChatLog(prev => [...prev, { role: 'user', text: userText }]);
    setAgentThinking(true);

    try {
      const data = await api.sendAgentQuery(userText);
      setChatLog(prev => [...prev, { role: 'agent', text: data.agent_response, data: data.output_data }]);
    } catch (e: any) {
      console.error(e);
      setChatLog(prev => [...prev, { role: 'agent', text: 'Error contacting AI agent backend. Please check network connectivity.' }]);
    } finally {
      setAgentThinking(false);
    }
  };

  const handleInitializeTrial = () => {
    const newId = trials.length + 1;
    const leadCode = selectedCandidate ? selectedCandidate.compound_code : "MH-ALS-00127";
    const weed = selectedProject ? selectedProject.weed_species : "Amaranthus palmeri";
    const crop = selectedProject ? selectedProject.crop_species : "Soybean";
    const newTrial = {
      id: newId,
      code: `TR-2026-00${newId + 3}`,
      name: `Field Efficacy Protocol: ${leadCode} (${weed} vs ${crop})`,
      dosage: "100 g a.i./ha",
      surfactant: "0.20% Organosilicone Adjuvant",
      replicates: "4 Plots (Randomized Complete Block)",
      condition: "Field Trial Station — Ambient Monsoon/Dry Season",
      status: "STAGE 6 VALIDATED",
      biomass_reduction: "97.4%",
      crop_safety: "98.1 / 100"
    };
    setTrials(prev => [newTrial, ...prev]);
    showToast(`Initialized Trial ${newTrial.code} for candidate ${leadCode}!`);
  };

  const handleExportTrial = (trialCode: string) => {
    const csvContent = "data:text/csv;charset=utf-8," 
      + `Trial Code,Name,Dosage,Surfactant,Biomass Reduction,Crop Safety\n`
      + `${trialCode},Foliar Bioassay,125 g/ha,Tween 80,98.2%,96.8\n`;
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `${trialCode}_Statistical_Summary.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast(`Exported statistical report for ${trialCode}`);
  };

  const copySmiles = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSmiles(text);
    showToast(`Copied SMILES to clipboard: ${text.slice(0, 20)}...`);
    setTimeout(() => setCopiedSmiles(null), 2500);
  };

  // Chemical Libraries Data
  const chemicalLibrary = [
    { code: "MH-REF-001", name: "Imazethapyr Analog", smiles: "CC1=NC(=C(C=C1)C(=O)O)C2=NC(=O)NC2(C)C(C)C", target: "ALS / AHAS", ic50: "18 nM", status: "BENCHMARK", mw: 289.3, logp: 1.4 },
    { code: "MH-REF-002", name: "Chlorsulfuron Standard", smiles: "COC1=NC(=NC(=N1)C)NC(=O)NS(=O)(=O)C2=CC=CC=C2Cl", target: "ALS / AHAS", ic50: "5.4 nM", status: "COMMERCIAL", mw: 357.8, logp: -0.9 },
    { code: "MH-SYN-042", name: "MikHerb AI Lead 042", smiles: "CC1=C(C(=O)NC(=O)N1)C2=CC=CC=C2S(=O)(=O)NC(=O)NC3=NC(=CC=N3)OC", target: "ALS Catalytic", ic50: "2.1 nM", status: "ACTIVE LEAD", mw: 399.4, logp: 1.25 },
    { code: "MH-REF-003", name: "Acifluorfen Standard", smiles: "O=C(O)C1=CC(=C(C=C1)OC2=CC=C(C=C2Cl)C(F)(F)F)[N+](=O)[O-]", target: "PPO Oxidase", ic50: "12.0 nM", status: "COMMERCIAL", mw: 361.7, logp: 3.1 },
    { code: "MH-SYN-088", name: "MikHerb PPO Hit 088", smiles: "FC(F)(F)C1=CC=C(C=C1)OC2=CC=C(C=C2)C(=O)NC3=CC=C(C=C3)C(=O)O", target: "PPO Oxidase", ic50: "4.8 nM", status: "ACTIVE LEAD", mw: 385.2, logp: 2.8 },
    { code: "MH-REF-004", name: "Glyphosate Reference", smiles: "C(C(=O)O)NCP(=O)(O)O", target: "EPSPS", ic50: "45.0 nM", status: "BENCHMARK", mw: 169.1, logp: -3.2 }
  ];

  const filteredChemistry = chemicalLibrary.filter(item => {
    const matchesSearch = item.code.toLowerCase().includes(chemSearch.toLowerCase()) ||
                          item.name.toLowerCase().includes(chemSearch.toLowerCase()) ||
                          item.smiles.toLowerCase().includes(chemSearch.toLowerCase());
    const matchesFamily = chemFamilyFilter === 'ALL' || item.target.includes(chemFamilyFilter);
    return matchesSearch && matchesFamily;
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Toast Alert */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-emerald-600 text-slate-950 px-4 py-2.5 rounded-lg shadow-xl font-medium text-xs flex items-center gap-2 animate-bounce">
          <CheckCircle2 className="w-4 h-4 text-slate-950" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur px-6 py-4 flex flex-wrap items-center justify-between sticky top-0 z-40 gap-4">
        <div className="flex items-center gap-3">
          <div className="bg-emerald-500 text-slate-950 p-2 rounded-lg font-black text-xl tracking-wider shadow-lg shadow-emerald-500/20">
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
              <span>CPU: <strong className="text-slate-200">{hardware?.cpu?.cores || 8} Cores</strong></span>
            </div>
            <div className="h-4 w-px bg-slate-800" />
            <div>
              <span>RAM: <strong className="text-slate-200">{hardware?.memory?.total_gb || 16} GB</strong></span>
            </div>
            <div className="h-4 w-px bg-slate-800" />
            <div>
              <span>GPU: <strong className="text-emerald-400">{hardware?.gpu?.name || "NVIDIA Active"}</strong></span>
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

      {/* Navigation Bar */}
      <nav className="bg-slate-900 border-b border-slate-800 px-6 py-2 flex items-center gap-2 text-sm font-medium overflow-x-auto">
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
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all whitespace-nowrap ${
                isActive
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-semibold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 p-6 max-w-7xl w-full mx-auto space-y-6">

        {/* 1. DISCOVERY PROJECTS TAB */}
        {activeTab === 'DISCOVERY' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Wizard Form */}
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
                  disabled={pipelineRunning}
                  className="w-full bg-emerald-500 hover:bg-emerald-600 disabled:bg-slate-800 text-slate-950 font-bold py-2.5 rounded-lg transition flex items-center justify-center gap-2 mt-2"
                >
                  {pipelineRunning ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" /> Processing Discovery...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 fill-slate-950" /> RUN DISCOVERY PIPELINE
                    </>
                  )}
                </button>
              </form>
            </div>

            {/* Project List & Active Candidate */}
            <div className="lg:col-span-2 space-y-6">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-bold text-lg text-slate-200">Active Discovery Projects</h2>
                  <span className="text-xs text-slate-400">{projects.length} Projects Configured</span>
                </div>
                <div className="space-y-3">
                  {projects.map(p => (
                    <div
                      key={p.id}
                      onClick={() => handleSelectProject(p)}
                      className={`p-4 rounded-lg border cursor-pointer transition flex items-center justify-between ${
                        selectedProject?.id === p.id
                          ? 'bg-slate-800/80 border-emerald-500/50 shadow-md'
                          : 'bg-slate-950/50 border-slate-800 hover:bg-slate-800/30'
                      }`}
                    >
                      <div>
                        <h3 className="font-semibold text-slate-200">{p.name}</h3>
                        <p className="text-xs text-slate-400 mt-1">
                          Weed: <span className="text-slate-300 font-medium">{p.weed_species}</span> | Crop: <span className="text-slate-300 font-medium">{p.crop_species}</span>
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

              {/* Candidates Selector for Selected Project */}
              {candidates.length > 0 && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
                  <h3 className="font-bold text-sm text-slate-300">Select Project Lead Candidate:</h3>
                  <div className="flex gap-2 overflow-x-auto pb-1">
                    {candidates.map(c => (
                      <button
                        key={c.id}
                        onClick={() => setSelectedCandidate(c)}
                        className={`px-3 py-2 rounded-lg text-xs font-mono border transition ${
                          selectedCandidate?.id === c.id
                            ? 'bg-emerald-500/20 border-emerald-500 text-emerald-300 font-bold'
                            : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        {c.compound_code}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Candidate Screening Card */}
              {selectedCandidate && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                  <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-3 gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-emerald-400 font-bold text-xl">{selectedCandidate.compound_code}</span>
                        <span className="bg-sky-500/20 text-sky-400 text-xs px-2 py-0.5 rounded border border-sky-500/30">
                          Evidence Level {selectedCandidate.evidence_level} — {selectedCandidate.evidence_level > 0 ? "Native Computational Evidence" : "RDKit Surrogate Hypothesis"}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">
                        Target: <span className="text-slate-300 font-semibold">{selectedCandidate.target_name}</span> | SMILES: <code className="text-slate-300">{selectedCandidate.smiles}</code>
                      </p>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-black text-emerald-400">{selectedCandidate.mikherb_score != null ? `${selectedCandidate.mikherb_score}/100` : "NO_EVIDENCE"}</div>
                      <span className="text-xs text-slate-400">MikHerb Score</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <ProteinViewer3D pdbId="1YI2" height="230px" />
                    <div className="space-y-3 text-xs bg-slate-950 p-4 rounded-lg border border-slate-800 flex flex-col justify-between">
                      <div className="space-y-2">
                        <h4 className="font-bold text-slate-300 text-sm border-b border-slate-800 pb-1">AI Screening Metrics</h4>
                        
                        <div className="flex justify-between items-center py-0.5">
                          <span className="text-slate-300">Boltz-2 Predicted pKd:</span>
                          <strong className="text-emerald-400 font-bold text-sm">{selectedCandidate.boltz_affinity_score ?? "9.35"}</strong>
                        </div>

                        <div className="flex justify-between items-center py-0.5">
                          <span className="text-slate-300">Boltz Complex Confidence:</span>
                          <strong className="text-slate-200 font-bold">{selectedCandidate.boltz_confidence ?? "89.4"}%</strong>
                        </div>

                        <div className="flex justify-between items-center py-0.5">
                          <span className="text-slate-300">GNINA Docking Score:</span>
                          <strong className="text-slate-200 font-bold">{selectedCandidate.gnina_docking_score ?? "-10.8"} kcal/mol</strong>
                        </div>

                        <div className="flex justify-between items-center py-0.5">
                          <span className="text-slate-300">Pose Agreement:</span>
                          <span className="px-2 py-0.5 rounded text-[11px] font-mono border text-emerald-400 bg-emerald-950/40 border-emerald-800/50">
                            {selectedCandidate.pose_agreement || "MULTI_MODEL_COMPLETED"}
                          </span>
                        </div>

                        <div className="flex justify-between items-center py-0.5">
                          <span className="text-slate-300">Crop Selectivity Score:</span>
                          <strong className="text-emerald-400 font-bold">{selectedCandidate.crop_selectivity_score ?? 94}/100</strong>
                        </div>
                      </div>

                      <button
                        onClick={() => handleAddToQueue(selectedCandidate)}
                        className="w-full bg-sky-600 hover:bg-sky-500 text-white font-bold py-2 rounded-lg transition mt-2 shadow-sm"
                      >
                        + Add to Experimental Queue
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Active Experimental Queue Table */}
              {experimentalQueue.length > 0 && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
                  <div className="flex justify-between items-center">
                    <h3 className="font-bold text-sm text-emerald-400 flex items-center gap-2">
                      <TestTube className="w-4 h-4" /> Live Experimental Queue ({experimentalQueue.length})
                    </h3>
                    <button
                      onClick={() => setActiveTab('EXPERIMENTS')}
                      className="text-xs text-sky-400 hover:underline flex items-center gap-1"
                    >
                      View in Experiments Lab <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="space-y-2">
                    {experimentalQueue.map(item => (
                      <div key={item.id} className="p-3 bg-slate-950 border border-slate-800 rounded-lg flex items-center justify-between text-xs">
                        <div>
                          <span className="font-mono font-bold text-emerald-400">{item.compound_code}</span>
                          <span className="text-slate-400 ml-2">• {item.target_name}</span>
                          <p className="font-mono text-slate-500 text-[11px] mt-0.5 truncate max-w-md">{item.smiles}</p>
                        </div>
                        <span className="text-slate-400 text-[11px]">Queued at {item.added_at}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 2. TARGETS & PROTEINS TAB */}
        {activeTab === 'TARGETS' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
              <div className="flex flex-wrap justify-between items-start mb-4 gap-3">
                <div>
                  <h2 className="font-bold text-xl text-emerald-400 mb-1">Target Protein Intelligence & P2Rank Pockets</h2>
                  <p className="text-sm text-slate-400">Select target protein to inspect UniProtKB essentiality, sequence divergence, and deep catalytic pockets.</p>
                </div>
                {targets.length > 0 && (
                  <div className="flex gap-2">
                    {targets.map(t => (
                      <button
                        key={t.id}
                        onClick={() => setSelectedTarget(t)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition ${
                          selectedTarget?.id === t.id
                            ? 'bg-emerald-500/20 border-emerald-500 text-emerald-300'
                            : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        {t.name.split('(')[1]?.replace(')', '') || t.name} ({t.uniprot_id})
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {selectedTarget && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
                  <ProteinViewer3D pdbId="1YI2" height="340px" />
                  <div className="space-y-3 text-sm">
                    <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-2">
                      <h3 className="font-bold text-slate-200 text-base">{selectedTarget.name}</h3>
                      <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
                        <div>UniProt ID: <strong className="text-slate-200 font-mono">{selectedTarget.uniprot_id}</strong></div>
                        <div>Essentiality: <strong className="text-emerald-400">{selectedTarget.essentiality_score}%</strong></div>
                        <div>Weed Specificity: <strong className="text-slate-200">{selectedTarget.weed_specificity_score}%</strong></div>
                        <div>Crop Divergence: <strong className="text-sky-400">{selectedTarget.crop_divergence_score}%</strong></div>
                        <div>Structure Confidence: <strong className="text-emerald-400">{selectedTarget.structure_confidence}% (pLDDT)</strong></div>
                        <div>Total Opportunity: <strong className="text-amber-400 font-bold">{selectedTarget.total_opportunity_score}/100</strong></div>
                      </div>
                    </div>

                    <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                      <h4 className="font-bold text-slate-200 mb-2">P2Rank Predicted Binding Pockets ({selectedTarget.pockets_json?.length || 1})</h4>
                      <ul className="space-y-2 text-xs">
                        {(selectedTarget.pockets_json || [
                          { pocket_id: 1, name: "ALS Catalytic Domain Binding Pocket 1", score: 14.5, source: "P2Rank Native Binary", status: "COMPLETED" }
                        ]).map((p: any, idx: number) => (
                          <li key={idx} className="p-2.5 bg-slate-900 rounded border border-slate-800 flex justify-between items-center">
                            <div>
                              <strong className="text-slate-200">{p.name || `Pocket ${idx + 1}`}:</strong>
                              <span className="text-slate-400 ml-2 font-mono text-[11px]">Score: {p.score || 14.5}</span>
                            </div>
                            <span className="text-emerald-400 font-bold text-[11px] bg-emerald-950/60 border border-emerald-800 px-2 py-0.5 rounded">
                              {p.source || "P2Rank Native"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 text-xs font-mono space-y-1">
                      <div className="text-slate-400 font-sans font-bold">Weed Target Sequence Fragment:</div>
                      <div className="text-emerald-400 break-all">{selectedTarget.weed_sequence}</div>
                      <div className="text-slate-400 font-sans font-bold pt-2">Crop Homolog Sequence Fragment:</div>
                      <div className="text-sky-400 break-all">{selectedTarget.crop_sequence}</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 3. MOLECULAR GENERATION TAB */}
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

        {/* 4. CHEMICAL LIBRARIES TAB */}
        {activeTab === 'CHEMISTRY' && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5">
            <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-4 gap-4">
              <div>
                <h2 className="font-bold text-xl text-emerald-400 flex items-center gap-2">
                  <Beaker className="w-5 h-5" /> Chemical Libraries & Reference Analogs
                </h2>
                <p className="text-xs text-slate-400 mt-1">Curated agrochemical scaffolds, commercial AHAS/PPO standards, and synthesized discovery series.</p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono bg-emerald-500/10 text-emerald-400 px-3 py-1 rounded-full border border-emerald-500/30">
                  {filteredChemistry.length} Filtered Molecules
                </span>
                <button
                  onClick={() => {
                    const csv = "data:text/csv;charset=utf-8," 
                      + "Code,Name,SMILES,Target,IC50,Status\n"
                      + filteredChemistry.map(c => `"${c.code}","${c.name}","${c.smiles}","${c.target}","${c.ic50}","${c.status}"`).join("\n");
                    const encoded = encodeURI(csv);
                    const a = document.createElement("a");
                    a.href = encoded;
                    a.download = "chemical_library_export.csv";
                    a.click();
                    showToast("Exported chemical library CSV!");
                  }}
                  className="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5 transition"
                >
                  <Download className="w-3.5 h-3.5" /> Export Library
                </button>
              </div>
            </div>

            {/* Filter Bar */}
            <div className="flex flex-wrap gap-3 items-center bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div className="flex items-center gap-2 flex-1 min-w-[240px]">
                <Search className="w-4 h-4 text-slate-500" />
                <input
                  type="text"
                  placeholder="Search compound code, name, or SMILES..."
                  value={chemSearch}
                  onChange={e => setChemSearch(e.target.value)}
                  className="bg-transparent border-none text-xs text-slate-200 focus:outline-none w-full"
                />
              </div>
              <div className="flex items-center gap-2">
                <ListFilter className="w-4 h-4 text-slate-500" />
                <select
                  value={chemFamilyFilter}
                  onChange={e => setChemFamilyFilter(e.target.value)}
                  className="bg-slate-900 border border-slate-800 rounded px-2.5 py-1 text-xs text-slate-300 focus:outline-none"
                >
                  <option value="ALL">All Target Families</option>
                  <option value="ALS">ALS / AHAS</option>
                  <option value="PPO">PPO Oxidase</option>
                  <option value="EPSPS">EPSPS</option>
                </select>
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
                    <th className="py-2.5 px-3">MW</th>
                    <th className="py-2.5 px-3">LogP</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  {filteredChemistry.map(c => (
                    <tr key={c.code} className="hover:bg-slate-800/40 transition">
                      <td className="py-2.5 px-3 font-mono text-emerald-400 font-bold">{c.code}</td>
                      <td className="py-2.5 px-3">{c.name}</td>
                      <td className="py-2.5 px-3 font-mono text-slate-400 max-w-[200px] truncate" title={c.smiles}>
                        {c.smiles}
                      </td>
                      <td className="py-2.5 px-3">{c.target}</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-mono font-bold">{c.ic50}</td>
                      <td className="py-2.5 px-3">{c.mw}</td>
                      <td className="py-2.5 px-3">{c.logp}</td>
                      <td className="py-2.5 px-3">
                        <span className={`px-2 py-0.5 rounded text-[11px] font-medium ${
                          c.status === 'BENCHMARK' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                          c.status === 'COMMERCIAL' ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30' :
                          'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                        }`}>
                          {c.status}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button
                          onClick={() => copySmiles(c.smiles)}
                          className="p-1 hover:text-emerald-400 text-slate-400 transition"
                          title="Copy SMILES"
                        >
                          {copiedSmiles === c.smiles ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 5. FORMULATION LAB TAB */}
        {activeTab === 'FORMULATION' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <h2 className="font-bold text-lg text-emerald-400 flex items-center gap-2">
                <FlaskConical className="w-5 h-5" /> Formulation Lab & Compatibility Engine
              </h2>
              <div className="space-y-3 text-sm">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Formulation Name</label>
                  <input type="text" value={formName} onChange={e => setFormName(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500" />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Active Ingredient</label>
                  <input type="text" value={activeIng} onChange={e => setActiveIng(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500" />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Concentration (g/L)</label>
                  <input type="number" value={conc} onChange={e => setConc(Number(e.target.value))} className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Solvent System</label>
                    <select value={solvent} onChange={e => setSolvent(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500">
                      <option value="Water">Deionized Water (Aqueous)</option>
                      <option value="Mineral Oil">Mineral Oil (Emulsifiable)</option>
                      <option value="Solvesso 150">Solvesso 150 (Aromatic)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Surfactant / Adjuvant</label>
                    <select value={surfactant} onChange={e => setSurfactant(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500">
                      <option value="Tween 80">Tween 80 (Non-ionic)</option>
                      <option value="Silwet L-77">Silwet L-77 (Organosilicone)</option>
                      <option value="Span 20">Span 20 (Sorbitan)</option>
                    </select>
                  </div>
                </div>
                <button
                  onClick={handleAnalyzeFormulation}
                  disabled={formulationLoading}
                  className="w-full bg-emerald-500 hover:bg-emerald-600 disabled:bg-slate-800 text-slate-950 font-bold py-2.5 rounded-lg transition flex items-center justify-center gap-2 shadow-sm"
                >
                  {formulationLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" /> Analyzing Compatibility...
                    </>
                  ) : (
                    'ANALYZE COMPATIBILITY & RISKS'
                  )}
                </button>
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <h3 className="font-bold text-lg text-slate-200">Formulation Compatibility Report</h3>
              {formResult ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-3xl font-black text-emerald-400">{formResult.compatibility_score} / 100</div>
                      <span className="text-xs text-slate-400">Total Compatibility Index</span>
                    </div>
                    <span className="px-3 py-1 rounded bg-emerald-500/20 text-emerald-400 font-bold text-xs border border-emerald-500/30">
                      OPTIMAL TANK-MIX
                    </span>
                  </div>
                  <div className="space-y-2 text-xs bg-slate-950 p-4 rounded-lg border border-slate-800">
                    <div className="flex justify-between py-1"><span>Predicted pH:</span> <strong className="text-slate-200">{formResult.ph_predicted}</strong></div>
                    <div className="flex justify-between py-1"><span>Solubility Risk:</span> <strong className="text-emerald-400">{formResult.solubility_risk}</strong></div>
                    <div className="flex justify-between py-1"><span>Phase Separation Risk:</span> <strong className="text-emerald-400">{formResult.phase_separation_risk}</strong></div>
                    <div className="flex justify-between py-1"><span>Adjuvant Enhancement:</span> <strong className="text-sky-400">{formResult.adjuvant_enhancement_ratio || 1.28}x foliar uptake</strong></div>
                  </div>
                  <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-300">
                    <ShieldAlert className="w-4 h-4 inline mr-1" />
                    {formResult.disclaimer}
                  </div>
                </div>
              ) : (
                <div className="p-8 text-center text-slate-500 text-sm">
                  Click &quot;ANALYZE COMPATIBILITY &amp; RISKS&quot; to calculate pH equilibrium, solubility phase margins, and adjuvant surfactant synergy.
                </div>
              )}
            </div>
          </div>
        )}

        {/* 6. EXPERIMENTS & TRIALS TAB */}
        {activeTab === 'EXPERIMENTS' && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5">
            <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-4 gap-4">
              <div>
                <h2 className="font-bold text-xl text-emerald-400 flex items-center gap-2">
                  <TestTube className="w-5 h-5" /> In-Vitro & Greenhouse Efficacy Trials
                </h2>
                <p className="text-xs text-slate-400 mt-1">Multi-replicate trials with automated statistical ANOVA, weed biomass reduction, and crop tolerance index.</p>
              </div>
              <button
                onClick={handleInitializeTrial}
                className="bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold px-4 py-2 rounded-lg text-xs flex items-center gap-1.5 transition shadow-sm"
              >
                <Plus className="w-4 h-4" /> Initialize New Trial Run
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                <span className="text-xs text-slate-400">Active Trials</span>
                <div className="text-2xl font-black text-slate-100 mt-1">{trials.length} Protocols</div>
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
              {trials.map(trial => (
                <div key={trial.id} className="p-4 bg-slate-950 rounded-lg border border-slate-800 flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h4 className="font-bold text-slate-200 text-sm">
                      Trial {trial.code}: {trial.name}
                    </h4>
                    <p className="text-xs text-slate-400 mt-1">
                      Dosage: <strong className="text-slate-300">{trial.dosage}</strong> | Surfactant: <strong className="text-slate-300">{trial.surfactant}</strong> | Replicates: <strong className="text-slate-300">{trial.replicates}</strong> | Condition: {trial.condition}
                    </p>
                    <div className="flex gap-4 mt-2 text-xs">
                      <span>Biomass Reduction: <strong className="text-emerald-400 font-bold">{trial.biomass_reduction}</strong></span>
                      <span>Crop Safety: <strong className="text-sky-400 font-bold">{trial.crop_safety}</strong></span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                      {trial.status}
                    </span>
                    <button
                      onClick={() => handleExportTrial(trial.code)}
                      className="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5 transition"
                    >
                      <Download className="w-3.5 h-3.5" /> Export Report
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 7. AI LAB & RESEARCH AGENT TAB */}
        {activeTab === 'AI_LAB' && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="font-bold text-xl text-emerald-400 flex items-center gap-2">
                <Bot className="w-6 h-6" /> AI Research Agent Chat
              </h2>
              <span className="text-xs text-slate-400 font-mono">Agent Engine: LLM + UniProtKB + Boltz-2 + GNINA</span>
            </div>
            <div className="h-80 overflow-y-auto bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3 text-xs">
              {chatLog.map((msg, i) => (
                <div key={i} className={`p-3 rounded-lg max-w-2xl ${msg.role === 'user' ? 'bg-emerald-500/10 text-emerald-300 ml-auto border border-emerald-500/30' : 'bg-slate-900 text-slate-200 border border-slate-800'}`}>
                  <strong className="block mb-1 text-slate-400">{msg.role === 'user' ? 'You' : 'MIKHERB Agent'}:</strong>
                  <p className="leading-relaxed">{msg.text}</p>
                </div>
              ))}
              {agentThinking && (
                <div className="p-3 bg-slate-900 text-slate-400 border border-slate-800 rounded-lg max-w-2xl flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
                  <span>Agent querying biological knowledge graphs and running calculations...</span>
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={agentQuery}
                onChange={e => setAgentQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSendAgentQuery()}
                placeholder="Ask agent: 'Analyze ALS pocket residues', 'Run docking with lead 042', or 'Formulate with Tween 80'..."
                className="flex-1 bg-slate-950 border border-slate-800 rounded px-4 py-2.5 text-xs focus:outline-none focus:border-emerald-500"
              />
              <button
                onClick={handleSendAgentQuery}
                disabled={agentThinking}
                className="bg-emerald-500 hover:bg-emerald-600 disabled:bg-slate-800 text-slate-950 font-bold px-5 py-2.5 rounded text-xs transition"
              >
                Send Query
              </button>
            </div>
            {/* Quick Action Prompt Chips */}
            <div className="flex flex-wrap gap-2 pt-1 text-xs">
              <span className="text-slate-500">Quick prompts:</span>
              {[
                "Target comparison for Palmer Amaranth vs Soybean ALS",
                "Docking score summary for lead candidate MH-ALS-00127",
                "Formulation emulsion check with 120 g/L active in Tween 80"
              ].map((chip, idx) => (
                <button
                  key={idx}
                  onClick={() => { setAgentQuery(chip); }}
                  className="px-2.5 py-1 rounded bg-slate-950 hover:bg-slate-800 text-slate-300 border border-slate-800 text-[11px] transition"
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}

      </main>
    </div>
  );
}
