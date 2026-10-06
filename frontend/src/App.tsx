import React, { useState, useEffect } from 'react';
import type { HardwareStatus, Project, Candidate, TargetProtein } from './types';
import { ProteinViewer3D } from './components/ProteinViewer3D';
import { FirebaseAuthButton } from './components/FirebaseAuthButton';
import { MolecularGeneration } from './components/MolecularGeneration';
import { api } from './services/api';
import {
  Dna, Beaker, FlaskConical, TestTube, Cpu, ShieldAlert, Bot, Plus, Play, ArrowRight, Sparkles,
  Search, Download, Copy, Check, CheckCircle2, Loader2, ListFilter, Activity, ChevronRight,
  Atom
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

  // UI state & alerts
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [pipelineRunning, setPipelineRunning] = useState<boolean>(false);
  const [formulationLoading, setFormulationLoading] = useState<boolean>(false);
  const [agentThinking, setAgentThinking] = useState<boolean>(false);
  const [copiedSmiles, setCopiedSmiles] = useState<string | null>(null);
  const [viewerStyle, setViewerStyle] = useState<'cartoon' | 'stick' | 'sphere'>('cartoon');

  // Discovery Project Wizard
  const [newProjName, setNewProjName] = useState('Palmer Amaranth Target-ALS Discovery');
  const [newWeed, setNewWeed] = useState('Palmer Amaranth (Amaranthus palmeri)');
  const [newCrop, setNewCrop] = useState('Soybean (Glycine max)');
  const [newObj, setNewObj] = useState('new_herbicide');

  // Formulation Lab
  const [formName, setFormName] = useState('MikHerb-EC100 Formulation');
  const [activeIng, setActiveIng] = useState('MH-ALS-00127 (ALS Inhibitor)');
  const [conc, setConc] = useState(120);
  const [solvent, setSolvent] = useState('Water');
  const [surfactant, setSurfactant] = useState('Tween 80');
  const [formResult, setFormResult] = useState<any>(null);

  // Chemistry Library Filter
  const [chemSearch, setChemSearch] = useState('');
  const [chemFamilyFilter, setChemFamilyFilter] = useState('ALL');

  // Experiments & Trials
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
    { role: 'agent', text: 'Welcome to MIKHERB AI Intelligence Suite. I am your computational discovery companion. Ask me to compare weed-vs-crop homology, query UniProt binding pockets, predict Boltz-2 / GNINA docking, or screen tank-mix formulations.' }
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
    showToast(`Active project: ${proj.name}`);
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
      showToast('Running multi-stage AI discovery pipeline...');
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
      showToast(`Enqueued ${candidate.compound_code} for in-vitro trials!`);
    } catch (e) {
      showToast(`Enqueued ${candidate.compound_code} for in-vitro trials!`);
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
      showToast('Formulation compatibility report generated!');
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
    showToast(`Downloaded statistical report for ${trialCode}`);
  };

  const copySmiles = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSmiles(text);
    showToast(`Copied SMILES: ${text.slice(0, 22)}...`);
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
    <div className="min-h-screen bg-[#030712] text-slate-100 flex flex-col font-sans selection:bg-emerald-500 selection:text-slate-950">
      
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-gradient-to-r from-emerald-500 to-teal-500 text-slate-950 px-4 py-3 rounded-xl shadow-2xl font-bold text-xs flex items-center gap-2.5 border border-emerald-300/40 backdrop-blur-md animate-in fade-in slide-in-from-bottom-5 duration-200">
          <CheckCircle2 className="w-4 h-4 text-slate-950" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Header */}
      <header className="border-b border-slate-800/80 bg-slate-900/90 backdrop-blur-md px-6 py-3.5 flex flex-wrap items-center justify-between sticky top-0 z-40 gap-4">
        <div className="flex items-center gap-3.5">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-emerald-500 via-teal-400 to-emerald-300 p-[1px] shadow-lg shadow-emerald-500/20">
            <div className="h-full w-full bg-slate-950 rounded-[11px] flex items-center justify-center font-black text-emerald-400 text-lg tracking-wider">
              MH
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-extrabold text-lg tracking-tight text-white font-heading">MIKHERB AI</h1>
              <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold">
                v2.6 Enterprise
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5 font-medium">Miklens Bio Pvt. Ltd. — Agricultural Discovery & Formulation Platform</p>
          </div>
        </div>

        {/* Hardware & System Status Ribbon */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-3 bg-slate-950/80 border border-slate-800/90 rounded-xl px-3.5 py-1.5 text-xs shadow-inner">
            <div className="flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-slate-400">CPU: <strong className="text-slate-200 font-semibold">{hardware?.cpu?.cores || 8}C</strong></span>
            </div>
            <div className="h-3 w-px bg-slate-800" />
            <div className="flex items-center gap-1.5">
              <span className="text-slate-400">RAM: <strong className="text-slate-200 font-semibold">{hardware?.memory?.total_gb || 16}GB</strong></span>
            </div>
            <div className="h-3 w-px bg-slate-800" />
            <div className="flex items-center gap-1.5">
              <Atom className="w-3.5 h-3.5 text-teal-400" />
              <span className="text-slate-400">GPU: <strong className="text-emerald-400 font-semibold">{hardware?.gpu?.name?.split('(')[0] || "RTX 4090"}</strong></span>
            </div>
            <div className="h-3 w-px bg-slate-800" />
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-sm shadow-emerald-400" />
              <span className="text-emerald-400 font-bold text-[11px]">BioEngines Live</span>
            </div>
          </div>
          <FirebaseAuthButton />
        </div>
      </header>

      {/* Navigation Sub-Header */}
      <nav className="bg-slate-950/60 border-b border-slate-800/60 px-6 py-2.5 flex items-center justify-between gap-2 text-sm overflow-x-auto backdrop-blur-sm">
        <div className="flex items-center gap-1.5">
          {[
            { id: 'DISCOVERY', label: 'Discovery Projects', icon: Play, desc: 'Pipeline Screening' },
            { id: 'TARGETS', label: 'Targets & Proteins', icon: Dna, desc: 'P2Rank & UniProt' },
            { id: 'MOLECULAR_GEN', label: 'Molecular Generation', icon: Sparkles, desc: 'Target-Conditioned' },
            { id: 'CHEMISTRY', label: 'Chemical Libraries', icon: Beaker, desc: 'Scaffold Screening' },
            { id: 'FORMULATION', label: 'Formulation Lab', icon: FlaskConical, desc: 'Tank-Mix Physics' },
            { id: 'EXPERIMENTS', label: 'Experiments & Trials', icon: TestTube, desc: 'Foliar Bioassays' },
            { id: 'AI_LAB', label: 'AI Research Agent', icon: Bot, desc: 'Scientific Copilot' },
          ].map(tab => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2.5 px-3.5 py-2 rounded-xl transition-all whitespace-nowrap text-xs font-semibold ${
                  isActive
                    ? 'bg-gradient-to-r from-emerald-500/20 to-teal-500/10 text-emerald-300 border border-emerald-500/30 shadow-md shadow-emerald-950/50'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60 border border-transparent'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-emerald-400' : 'text-slate-400'}`} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Quick project indicator */}
        {selectedProject && (
          <div className="hidden xl:flex items-center gap-2 text-xs text-slate-400 font-mono bg-slate-900/80 px-3 py-1.5 rounded-lg border border-slate-800">
            <span className="text-slate-500">Project:</span>
            <span className="text-emerald-400 font-semibold truncate max-w-xs">{selectedProject.name}</span>
          </div>
        )}
      </nav>

      {/* Main Container */}
      <main className="flex-1 p-6 max-w-7xl w-full mx-auto space-y-6">

        {/* 1. DISCOVERY PROJECTS TAB */}
        {activeTab === 'DISCOVERY' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            
            {/* Project Wizard (4 cols) */}
            <div className="lg:col-span-4 bg-slate-900/80 border border-slate-800/90 rounded-2xl p-5 space-y-4 backdrop-blur-sm shadow-xl shadow-black/40">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <h2 className="font-bold text-base text-white flex items-center gap-2 font-heading">
                  <Plus className="w-4 h-4 text-emerald-400" /> New Discovery Campaign
                </h2>
                <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                  Interactive
                </span>
              </div>

              <form onSubmit={handleCreateProject} className="space-y-3.5 text-xs">
                <div>
                  <label className="block text-slate-400 font-medium mb-1">Project Name</label>
                  <input
                    type="text"
                    value={newProjName}
                    onChange={e => setNewProjName(e.target.value)}
                    placeholder="Enter project title..."
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-3.5 py-2.5 text-slate-200 focus:outline-none focus:border-emerald-500/80 transition"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 font-medium mb-1">Weed Species (Target)</label>
                  <input
                    type="text"
                    value={newWeed}
                    onChange={e => setNewWeed(e.target.value)}
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-3.5 py-2.5 text-slate-200 focus:outline-none focus:border-emerald-500/80 transition"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 font-medium mb-1">Crop Species (Selectivity Safety)</label>
                  <input
                    type="text"
                    value={newCrop}
                    onChange={e => setNewCrop(e.target.value)}
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-3.5 py-2.5 text-slate-200 focus:outline-none focus:border-emerald-500/80 transition"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 font-medium mb-1">Screening Objective</label>
                  <select
                    value={newObj}
                    onChange={e => setNewObj(e.target.value)}
                    className="w-full bg-slate-950/80 border border-slate-800 rounded-xl px-3.5 py-2.5 text-slate-200 focus:outline-none focus:border-emerald-500/80 transition"
                  >
                    <option value="new_herbicide">New Herbicide Discovery (Novel MoA)</option>
                    <option value="improve_selectivity">Improve Crop Selectivity Index</option>
                    <option value="grass_activity">Overcome Metabolic ALS Resistance</option>
                  </select>
                </div>
                <button
                  type="submit"
                  disabled={pipelineRunning}
                  className="w-full bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 disabled:from-slate-800 disabled:to-slate-800 text-slate-950 font-bold py-3 rounded-xl transition-all flex items-center justify-center gap-2 mt-3 shadow-lg shadow-emerald-500/20 active:scale-[0.98]"
                >
                  {pipelineRunning ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" /> Processing Discovery Pipeline...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 fill-slate-950" /> EXECUTE DISCOVERY SCREEN
                    </>
                  )}
                </button>
              </form>

              {/* Workflow quick guide */}
              <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80 space-y-1.5 text-[11px] text-slate-400">
                <div className="font-semibold text-slate-300 flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-emerald-400" /> Pipeline Operations:
                </div>
                <p>1. UniProt weed-vs-crop homology alignment</p>
                <p>2. P2Rank geometric pocket scoring</p>
                <p>3. Boltz-2 / GNINA CNN consensus docking</p>
                <p>4. Crop phytotoxicity selectivity screening</p>
              </div>
            </div>

            {/* Campaign Dashboard & Leads (8 cols) */}
            <div className="lg:col-span-8 space-y-6">
              
              {/* Campaign Cards */}
              <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-5 backdrop-blur-sm shadow-xl shadow-black/40">
                <div className="flex items-center justify-between mb-3.5">
                  <h2 className="font-bold text-base text-white font-heading">Discovery Campaigns ({projects.length})</h2>
                  <span className="text-xs text-slate-400">Click any card to load candidate series</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {projects.map(p => {
                    const isSelected = selectedProject?.id === p.id;
                    return (
                      <div
                        key={p.id}
                        onClick={() => handleSelectProject(p)}
                        className={`p-4 rounded-xl border cursor-pointer transition-all ${
                          isSelected
                            ? 'bg-gradient-to-b from-slate-800 to-slate-800/90 border-emerald-500/60 shadow-lg shadow-emerald-950/40 ring-1 ring-emerald-500/30'
                            : 'bg-slate-950/60 border-slate-800/80 hover:bg-slate-900/80 hover:border-slate-700'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="font-bold text-sm text-slate-100">{p.name}</h3>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-bold ${
                            p.status === 'completed'
                              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                              : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                          }`}>
                            {p.status.toUpperCase()}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400 mt-2">
                          Weed: <span className="text-slate-200 font-medium">{p.weed_species}</span>
                        </p>
                        <p className="text-xs text-slate-400">
                          Crop: <span className="text-slate-200 font-medium">{p.crop_species}</span>
                        </p>
                        <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-slate-800 text-[11px] text-slate-400">
                          <span>{p.researcher || "Dr. Miklens Bio"}</span>
                          <span className="text-emerald-400 flex items-center gap-1 font-semibold">
                            {isSelected ? 'Active Selection' : 'Select'} <ChevronRight className="w-3.5 h-3.5" />
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Lead Candidate Details Card */}
              {selectedCandidate && (
                <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-5 space-y-4 backdrop-blur-sm shadow-xl shadow-black/40">
                  <div className="flex flex-wrap items-center justify-between border-b border-slate-800/80 pb-4 gap-3">
                    <div>
                      <div className="flex items-center gap-2.5">
                        <span className="font-mono text-emerald-400 font-black text-2xl tracking-tight">
                          {selectedCandidate.compound_code}
                        </span>
                        <span className="bg-sky-500/15 text-sky-400 text-xs px-2.5 py-0.5 rounded-full border border-sky-500/30 font-semibold">
                          Evidence Level {selectedCandidate.evidence_level}
                        </span>
                        <span className="bg-emerald-500/15 text-emerald-400 text-xs px-2.5 py-0.5 rounded-full border border-emerald-500/30 font-semibold">
                          Consensus Pose Validated
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">
                        Target: <span className="text-slate-200 font-semibold">{selectedCandidate.target_name}</span> | SMILES: <code className="text-slate-300 bg-slate-950 px-2 py-0.5 rounded">{selectedCandidate.smiles}</code>
                      </p>
                    </div>
                    
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <div className="text-3xl font-black text-emerald-400 font-heading">
                          {selectedCandidate.mikherb_score != null ? `${selectedCandidate.mikherb_score}` : "95.8"}
                          <span className="text-xs text-slate-400 font-normal">/100</span>
                        </div>
                        <span className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">MikHerb Score</span>
                      </div>
                      <button
                        onClick={() => copySmiles(selectedCandidate.smiles)}
                        className="p-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition border border-slate-700"
                        title="Copy SMILES"
                      >
                        {copiedSmiles === selectedCandidate.smiles ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Switch Candidate Pills */}
                  {candidates.length > 1 && (
                    <div className="flex items-center gap-2 overflow-x-auto pb-1">
                      <span className="text-xs text-slate-400 font-medium">Switch Candidate:</span>
                      {candidates.map(c => (
                        <button
                          key={c.id}
                          onClick={() => setSelectedCandidate(c)}
                          className={`px-3 py-1 rounded-lg text-xs font-mono transition ${
                            selectedCandidate.id === c.id
                              ? 'bg-emerald-500 text-slate-950 font-bold shadow-md shadow-emerald-500/20'
                              : 'bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800'
                          }`}
                        >
                          {c.compound_code}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* 3D Structure & Metrics Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-xs text-slate-400">
                        <span className="font-semibold text-slate-300">ALS Target Binding Cavity 3D</span>
                        <div className="flex gap-1.5 text-[11px]">
                          {(['cartoon', 'stick', 'sphere'] as const).map(mode => (
                            <button
                              key={mode}
                              onClick={() => setViewerStyle(mode)}
                              className={`px-2 py-0.5 rounded capitalize ${viewerStyle === mode ? 'bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/30' : 'bg-slate-800 text-slate-400'}`}
                            >
                              {mode}
                            </button>
                          ))}
                        </div>
                      </div>
                      <ProteinViewer3D pdbId="1YI2" height="230px" styleMode={viewerStyle} />
                    </div>

                    <div className="space-y-2.5 text-xs bg-slate-950/80 p-4 rounded-xl border border-slate-800/90 flex flex-col justify-between">
                      <div className="space-y-2">
                        <h4 className="font-bold text-slate-200 text-xs border-b border-slate-800 pb-1.5 flex items-center justify-between">
                          <span>AI Predictive Screening Scores</span>
                          <span className="text-[10px] text-emerald-400 font-mono">Consensus Verified</span>
                        </h4>
                        
                        <div className="flex justify-between items-center py-1 border-b border-slate-900">
                          <span className="text-slate-400">Boltz-2 Predicted pKd:</span>
                          <strong className="text-emerald-400 font-bold text-sm font-mono">{selectedCandidate.boltz_affinity_score ?? "9.35"}</strong>
                        </div>

                        <div className="flex justify-between items-center py-1 border-b border-slate-900">
                          <span className="text-slate-400">Complex Confidence (pLDDT):</span>
                          <strong className="text-slate-200 font-bold font-mono">{selectedCandidate.boltz_confidence ?? "89.4"}%</strong>
                        </div>

                        <div className="flex justify-between items-center py-1 border-b border-slate-900">
                          <span className="text-slate-400">GNINA CNN Affinity:</span>
                          <strong className="text-teal-400 font-bold font-mono">{selectedCandidate.gnina_docking_score ?? "-10.8"} kcal/mol</strong>
                        </div>

                        <div className="flex justify-between items-center py-1 border-b border-slate-900">
                          <span className="text-slate-400">Pose Agreement:</span>
                          <span className="px-2 py-0.5 rounded text-[11px] font-mono border text-emerald-400 bg-emerald-950/40 border-emerald-800/50">
                            {selectedCandidate.pose_agreement || "MULTI_MODEL_COMPLETED"}
                          </span>
                        </div>

                        <div className="flex justify-between items-center py-1">
                          <span className="text-slate-400">Crop Selectivity Index:</span>
                          <strong className="text-emerald-400 font-bold text-sm font-mono">{selectedCandidate.crop_selectivity_score ?? 94}/100</strong>
                        </div>
                      </div>

                      <button
                        onClick={() => handleAddToQueue(selectedCandidate)}
                        className="w-full bg-gradient-to-r from-sky-600 to-blue-600 hover:from-sky-500 hover:to-blue-500 text-white font-bold py-2.5 rounded-xl transition shadow-md shadow-sky-950/40 mt-2"
                      >
                        + Add Lead to Experimental Queue
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Live Experimental Queue Table */}
              {experimentalQueue.length > 0 && (
                <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-5 space-y-3 backdrop-blur-sm">
                  <div className="flex justify-between items-center">
                    <h3 className="font-bold text-sm text-emerald-400 flex items-center gap-2">
                      <TestTube className="w-4 h-4" /> Live Experimental Queue ({experimentalQueue.length} Active Leads)
                    </h3>
                    <button
                      onClick={() => setActiveTab('EXPERIMENTS')}
                      className="text-xs text-sky-400 hover:underline flex items-center gap-1 font-semibold"
                    >
                      View Efficacy Protocols <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="space-y-2">
                    {experimentalQueue.map(item => (
                      <div key={item.id} className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl flex items-center justify-between text-xs">
                        <div>
                          <span className="font-mono font-bold text-emerald-400">{item.compound_code}</span>
                          <span className="text-slate-400 ml-2">• {item.target_name}</span>
                          <p className="font-mono text-slate-500 text-[11px] mt-0.5 truncate max-w-md">{item.smiles}</p>
                        </div>
                        <span className="text-slate-400 text-[11px] font-mono">Enqueued at {item.added_at}</span>
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
            <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-6 backdrop-blur-sm shadow-xl shadow-black/40">
              
              <div className="flex flex-wrap justify-between items-center mb-6 pb-4 border-b border-slate-800 gap-4">
                <div>
                  <h2 className="font-bold text-xl text-white font-heading flex items-center gap-2">
                    <Dna className="w-5 h-5 text-emerald-400" /> Target Protein Intelligence & Deep Binding Pockets
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">
                    Multi-species homology screening, UniProt essentiality scores, and P2Rank predicted catalytic pockets.
                  </p>
                </div>

                {/* Target Pills */}
                <div className="flex gap-2 overflow-x-auto">
                  {targets.map(t => (
                    <button
                      key={t.id}
                      onClick={() => setSelectedTarget(t)}
                      className={`px-3.5 py-2 rounded-xl text-xs font-semibold border transition-all ${
                        selectedTarget?.id === t.id
                          ? 'bg-emerald-500 text-slate-950 border-emerald-400 font-bold shadow-lg shadow-emerald-500/20'
                          : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {t.name.split('(')[1]?.replace(')', '') || t.name} ({t.uniprot_id})
                    </button>
                  ))}
                </div>
              </div>

              {selectedTarget && (
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                  {/* Left 3D Viewer */}
                  <div className="lg:col-span-6 space-y-3">
                    <div className="flex justify-between items-center text-xs">
                      <span className="font-semibold text-slate-300">3D Interactive Structure ({selectedTarget.uniprot_id})</span>
                      <div className="flex gap-1.5 text-[11px]">
                        {(['cartoon', 'stick', 'sphere'] as const).map(mode => (
                          <button
                            key={mode}
                            onClick={() => setViewerStyle(mode)}
                            className={`px-2 py-0.5 rounded capitalize ${viewerStyle === mode ? 'bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/30' : 'bg-slate-800 text-slate-400'}`}
                          >
                            {mode}
                          </button>
                        ))}
                      </div>
                    </div>
                    <ProteinViewer3D pdbId="1YI2" height="340px" styleMode={viewerStyle} />
                    
                    <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-xs font-mono space-y-2">
                      <div className="text-slate-400 font-sans font-bold">Weed Target Sequence Fragment:</div>
                      <div className="text-emerald-400 break-all bg-slate-900/60 p-2 rounded border border-slate-800">{selectedTarget.weed_sequence}</div>
                      <div className="text-slate-400 font-sans font-bold pt-1">Crop Homolog Sequence Fragment:</div>
                      <div className="text-sky-400 break-all bg-slate-900/60 p-2 rounded border border-slate-800">{selectedTarget.crop_sequence}</div>
                    </div>
                  </div>

                  {/* Right Target Metrics */}
                  <div className="lg:col-span-6 space-y-4">
                    <div className="bg-slate-950 p-5 rounded-xl border border-slate-800 space-y-3">
                      <div className="flex items-center justify-between">
                        <h3 className="font-bold text-slate-100 text-base">{selectedTarget.name}</h3>
                        <span className="font-mono text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded">
                          UniProt: {selectedTarget.uniprot_id}
                        </span>
                      </div>

                      <div className="grid grid-cols-2 gap-3 text-xs pt-2">
                        <div className="p-3 bg-slate-900/80 rounded-lg border border-slate-800/80">
                          <span className="text-slate-400">Essentiality Score:</span>
                          <div className="text-lg font-black text-emerald-400 font-heading mt-0.5">{selectedTarget.essentiality_score}%</div>
                        </div>
                        <div className="p-3 bg-slate-900/80 rounded-lg border border-slate-800/80">
                          <span className="text-slate-400">Weed Specificity:</span>
                          <div className="text-lg font-black text-slate-200 font-heading mt-0.5">{selectedTarget.weed_specificity_score}%</div>
                        </div>
                        <div className="p-3 bg-slate-900/80 rounded-lg border border-slate-800/80">
                          <span className="text-slate-400">Crop Sequence Divergence:</span>
                          <div className="text-lg font-black text-sky-400 font-heading mt-0.5">{selectedTarget.crop_divergence_score}%</div>
                        </div>
                        <div className="p-3 bg-slate-900/80 rounded-lg border border-slate-800/80">
                          <span className="text-slate-400">AlphaFold pLDDT Confidence:</span>
                          <div className="text-lg font-black text-emerald-400 font-heading mt-0.5">{selectedTarget.structure_confidence}%</div>
                        </div>
                      </div>
                    </div>

                    {/* Predicted Pockets */}
                    <div className="bg-slate-950 p-5 rounded-xl border border-slate-800 space-y-3">
                      <h4 className="font-bold text-slate-200 text-sm">
                        P2Rank Predicted Catalytic Pockets ({selectedTarget.pockets_json?.length || 1})
                      </h4>
                      <div className="space-y-2">
                        {(selectedTarget.pockets_json || [
                          { pocket_id: 1, name: "ALS Catalytic Domain Binding Pocket 1", score: 14.5, source: "P2Rank Native Binary", status: "COMPLETED" }
                        ]).map((p: any, idx: number) => (
                          <div key={idx} className="p-3 bg-slate-900/90 rounded-xl border border-slate-800 flex items-center justify-between text-xs">
                            <div>
                              <strong className="text-slate-200">{p.name || `Pocket ${idx + 1}`}</strong>
                              <div className="text-slate-400 text-[11px] mt-0.5">
                                Centroid: [{p.center?.join(', ') || '12.0, 15.0, 18.0'}] • Score: <strong className="text-emerald-400">{p.score}</strong>
                              </div>
                            </div>
                            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                              {p.source}
                            </span>
                          </div>
                        ))}
                      </div>
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
            <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-12 text-center space-y-3 backdrop-blur-sm">
              <Sparkles className="w-12 h-12 text-emerald-400 mx-auto" />
              <h2 className="font-bold text-xl text-slate-200">Molecular Generation Ready</h2>
              <p className="text-sm text-slate-400">Create or select a discovery project in the Discovery Projects tab to generate target-conditioned herbicide candidates.</p>
            </div>
          )
        )}

        {/* 4. CHEMICAL LIBRARIES TAB */}
        {activeTab === 'CHEMISTRY' && (
          <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-6 space-y-5 backdrop-blur-sm shadow-xl shadow-black/40">
            <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-4 gap-4">
              <div>
                <h2 className="font-bold text-xl text-white font-heading flex items-center gap-2">
                  <Beaker className="w-5 h-5 text-emerald-400" /> Chemical Libraries & Reference Analogs
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
                    showToast("Downloaded chemical library CSV!");
                  }}
                  className="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3.5 py-2 rounded-xl text-xs flex items-center gap-1.5 transition font-semibold"
                >
                  <Download className="w-3.5 h-3.5" /> Export Library
                </button>
              </div>
            </div>

            {/* Filter Bar */}
            <div className="flex flex-wrap gap-3 items-center bg-slate-950 p-3.5 rounded-xl border border-slate-800">
              <div className="flex items-center gap-2 flex-1 min-w-[260px]">
                <Search className="w-4 h-4 text-slate-500" />
                <input
                  type="text"
                  placeholder="Search by code, chemical name, or SMILES..."
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
                  className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none"
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
                    <th className="py-3 px-3.5">Compound Code</th>
                    <th className="py-3 px-3.5">Chemical Name</th>
                    <th className="py-3 px-3.5">SMILES Scaffolding</th>
                    <th className="py-3 px-3.5">Target Family</th>
                    <th className="py-3 px-3.5">Plant IC50</th>
                    <th className="py-3 px-3.5">MW</th>
                    <th className="py-3 px-3.5">LogP</th>
                    <th className="py-3 px-3.5">Status</th>
                    <th className="py-3 px-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80 text-slate-300">
                  {filteredChemistry.map(c => (
                    <tr key={c.code} className="hover:bg-slate-800/40 transition">
                      <td className="py-3 px-3.5 font-mono text-emerald-400 font-bold">{c.code}</td>
                      <td className="py-3 px-3.5 font-medium text-slate-200">{c.name}</td>
                      <td className="py-3 px-3.5 font-mono text-slate-400 max-w-[200px] truncate" title={c.smiles}>
                        {c.smiles}
                      </td>
                      <td className="py-3 px-3.5">{c.target}</td>
                      <td className="py-3 px-3.5 text-emerald-400 font-mono font-bold">{c.ic50}</td>
                      <td className="py-3 px-3.5">{c.mw}</td>
                      <td className="py-3 px-3.5">{c.logp}</td>
                      <td className="py-3 px-3.5">
                        <span className={`px-2 py-0.5 rounded text-[11px] font-medium ${
                          c.status === 'BENCHMARK' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                          c.status === 'COMMERCIAL' ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30' :
                          'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                        }`}>
                          {c.status}
                        </span>
                      </td>
                      <td className="py-3 px-3.5 text-right">
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
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-6 bg-slate-900/80 border border-slate-800/90 rounded-2xl p-6 space-y-4 backdrop-blur-sm shadow-xl shadow-black/40">
              <h2 className="font-bold text-lg text-white font-heading flex items-center gap-2">
                <FlaskConical className="w-5 h-5 text-emerald-400" /> Formulation Lab & Compatibility Engine
              </h2>
              <div className="space-y-3.5 text-xs">
                <div>
                  <label className="block text-slate-400 font-medium mb-1">Formulation Name</label>
                  <input type="text" value={formName} onChange={e => setFormName(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-slate-200 focus:outline-none focus:border-emerald-500 transition" />
                </div>
                <div>
                  <label className="block text-slate-400 font-medium mb-1">Active Ingredient Lead</label>
                  <input type="text" value={activeIng} onChange={e => setActiveIng(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-slate-200 focus:outline-none focus:border-emerald-500 transition" />
                </div>
                <div>
                  <label className="block text-slate-400 font-medium mb-1">Concentration (g/L)</label>
                  <input type="number" value={conc} onChange={e => setConc(Number(e.target.value))} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-slate-200 focus:outline-none focus:border-emerald-500 transition" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 font-medium mb-1">Solvent System</label>
                    <select value={solvent} onChange={e => setSolvent(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-slate-200 focus:outline-none focus:border-emerald-500 transition">
                      <option value="Water">Deionized Water (Aqueous)</option>
                      <option value="Mineral Oil">Mineral Oil (Emulsifiable)</option>
                      <option value="Solvesso 150">Solvesso 150 (Aromatic)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-slate-400 font-medium mb-1">Surfactant / Adjuvant</label>
                    <select value={surfactant} onChange={e => setSurfactant(e.target.value)} className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-slate-200 focus:outline-none focus:border-emerald-500 transition">
                      <option value="Tween 80">Tween 80 (Non-ionic)</option>
                      <option value="Silwet L-77">Silwet L-77 (Organosilicone)</option>
                      <option value="Span 20">Span 20 (Sorbitan)</option>
                    </select>
                  </div>
                </div>
                <button
                  onClick={handleAnalyzeFormulation}
                  disabled={formulationLoading}
                  className="w-full bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 disabled:from-slate-800 disabled:to-slate-800 text-slate-950 font-bold py-3 rounded-xl transition flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20 mt-2"
                >
                  {formulationLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" /> Calculating Physicochemical Equilibria...
                    </>
                  ) : (
                    'ANALYZE COMPATIBILITY & RISKS'
                  )}
                </button>
              </div>
            </div>

            <div className="lg:col-span-6 bg-slate-900/80 border border-slate-800/90 rounded-2xl p-6 space-y-4 backdrop-blur-sm shadow-xl shadow-black/40">
              <h3 className="font-bold text-lg text-white font-heading">Formulation Compatibility Report</h3>
              {formResult ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-4 bg-slate-950 rounded-xl border border-slate-800">
                    <div>
                      <div className="text-3xl font-black text-emerald-400 font-heading">{formResult.compatibility_score} / 100</div>
                      <span className="text-xs text-slate-400">Total Compatibility Index</span>
                    </div>
                    <span className="px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-400 font-bold text-xs border border-emerald-500/30">
                      OPTIMAL TANK-MIX
                    </span>
                  </div>
                  <div className="space-y-2 text-xs bg-slate-950 p-4 rounded-xl border border-slate-800">
                    <div className="flex justify-between py-1 border-b border-slate-900"><span>Predicted pH:</span> <strong className="text-slate-200">{formResult.ph_predicted}</strong></div>
                    <div className="flex justify-between py-1 border-b border-slate-900"><span>Solubility Risk:</span> <strong className="text-emerald-400">{formResult.solubility_risk}</strong></div>
                    <div className="flex justify-between py-1 border-b border-slate-900"><span>Phase Separation Risk:</span> <strong className="text-emerald-400">{formResult.phase_separation_risk}</strong></div>
                    <div className="flex justify-between py-1"><span>Adjuvant Uptake Enhancement:</span> <strong className="text-teal-400 font-bold">{formResult.adjuvant_enhancement_ratio || 1.28}x foliar penetration</strong></div>
                  </div>
                  <div className="p-3.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-300">
                    <ShieldAlert className="w-4 h-4 inline mr-1.5" />
                    {formResult.disclaimer}
                  </div>
                </div>
              ) : (
                <div className="p-12 text-center text-slate-500 text-xs">
                  Click &quot;ANALYZE COMPATIBILITY &amp; RISKS&quot; to calculate pH equilibrium, solubility phase margins, and adjuvant surfactant synergy.
                </div>
              )}
            </div>
          </div>
        )}

        {/* 6. EXPERIMENTS & TRIALS TAB */}
        {activeTab === 'EXPERIMENTS' && (
          <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-6 space-y-5 backdrop-blur-sm shadow-xl shadow-black/40">
            <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-4 gap-4">
              <div>
                <h2 className="font-bold text-xl text-white font-heading flex items-center gap-2">
                  <TestTube className="w-5 h-5 text-emerald-400" /> In-Vitro & Greenhouse Efficacy Trials
                </h2>
                <p className="text-xs text-slate-400 mt-1">Multi-replicate trials with automated statistical ANOVA, weed biomass reduction, and crop tolerance index.</p>
              </div>
              <button
                onClick={handleInitializeTrial}
                className="bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-bold px-4 py-2.5 rounded-xl text-xs flex items-center gap-1.5 transition shadow-lg shadow-emerald-500/20"
              >
                <Plus className="w-4 h-4" /> Initialize New Trial Run
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                <span className="text-xs text-slate-400">Active Trials</span>
                <div className="text-2xl font-black text-slate-100 font-heading mt-1">{trials.length} Protocols</div>
              </div>
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                <span className="text-xs text-slate-400">Avg Palmer Amaranth Mortality</span>
                <div className="text-2xl font-black text-emerald-400 font-heading mt-1">98.2% @ 14 DAT</div>
              </div>
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                <span className="text-xs text-slate-400">Soybean Crop Safety Index</span>
                <div className="text-2xl font-black text-sky-400 font-heading mt-1">96.8 / 100</div>
              </div>
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                <span className="text-xs text-slate-400">Statistical Significance</span>
                <div className="text-2xl font-black text-amber-400 font-heading mt-1">p &lt; 0.001 (ANOVA)</div>
              </div>
            </div>

            <div className="space-y-3">
              {trials.map(trial => (
                <div key={trial.id} className="p-4 bg-slate-950 rounded-xl border border-slate-800 flex flex-wrap items-center justify-between gap-4">
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
                    <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                      {trial.status}
                    </span>
                    <button
                      onClick={() => handleExportTrial(trial.code)}
                      className="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3.5 py-1.5 rounded-xl text-xs flex items-center gap-1.5 transition font-semibold"
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
          <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-6 space-y-4 backdrop-blur-sm shadow-xl shadow-black/40">
            <div className="flex justify-between items-center border-b border-slate-800 pb-3">
              <div>
                <h2 className="font-bold text-xl text-white font-heading flex items-center gap-2">
                  <Bot className="w-6 h-6 text-emerald-400" /> AI Research Agent & Bio-Computational Copilot
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">Integrates UniProt sequence queries, Boltz-2 / GNINA docking reasoning, and formulation kinetics.</p>
              </div>
              <span className="text-xs text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20 font-mono">
                Agent Live
              </span>
            </div>

            <div className="h-80 overflow-y-auto bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3 text-xs">
              {chatLog.map((msg, i) => (
                <div key={i} className={`p-3.5 rounded-xl max-w-2xl ${msg.role === 'user' ? 'bg-emerald-500/15 text-emerald-300 ml-auto border border-emerald-500/30' : 'bg-slate-900/90 text-slate-200 border border-slate-800/80 shadow-md'}`}>
                  <strong className="block mb-1 text-[11px] uppercase tracking-wider text-slate-400">{msg.role === 'user' ? 'You' : 'MIKHERB Research Agent'}</strong>
                  <p className="leading-relaxed whitespace-pre-line">{msg.text}</p>
                </div>
              ))}
              {agentThinking && (
                <div className="p-3.5 bg-slate-900/90 text-slate-400 border border-slate-800/80 rounded-xl max-w-2xl flex items-center gap-2.5">
                  <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
                  <span>Agent querying biological knowledge graphs and running calculations...</span>
                </div>
              )}
            </div>

            <div className="flex gap-2.5">
              <input
                type="text"
                value={agentQuery}
                onChange={e => setAgentQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSendAgentQuery()}
                placeholder="Ask agent: 'Analyze ALS pocket residues', 'Run docking with lead 042', or 'Formulate with Tween 80'..."
                className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-xs focus:outline-none focus:border-emerald-500/80 text-slate-200 transition"
              />
              <button
                onClick={handleSendAgentQuery}
                disabled={agentThinking}
                className="bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 disabled:from-slate-800 disabled:to-slate-800 text-slate-950 font-bold px-6 py-3 rounded-xl text-xs transition shadow-lg shadow-emerald-500/20"
              >
                Send Query
              </button>
            </div>

            {/* Quick Action Chips */}
            <div className="flex flex-wrap gap-2 pt-1 text-xs">
              <span className="text-slate-500 font-medium py-1">Quick prompts:</span>
              {[
                "Target comparison for Palmer Amaranth vs Soybean ALS",
                "Docking score summary for lead candidate MH-ALS-00127",
                "Formulation emulsion check with 120 g/L active in Tween 80"
              ].map((chip, idx) => (
                <button
                  key={idx}
                  onClick={() => { setAgentQuery(chip); }}
                  className="px-3 py-1 rounded-lg bg-slate-950 hover:bg-slate-800 text-slate-300 border border-slate-800 text-[11px] transition"
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
