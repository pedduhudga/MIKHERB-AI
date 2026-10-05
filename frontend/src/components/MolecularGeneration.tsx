import React, { useState, useEffect } from 'react';
import type { Project, TargetProtein, MolecularGenerationRun, GeneratedMolecule } from '../types';
import { api } from '../services/api';
import { Sparkles, Play, CheckCircle2, AlertCircle, RefreshCw, Copy, Check } from 'lucide-react';

interface Props {
  project: Project;
  targets: TargetProtein[];
}

export const MolecularGeneration: React.FC<Props> = ({ project, targets }) => {
  const [runs, setRuns] = useState<MolecularGenerationRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<MolecularGenerationRun | null>(null);
  const [molecules, setMolecules] = useState<GeneratedMolecule[]>([]);
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [copiedSmiles, setCopiedSmiles] = useState<string | null>(null);

  // Form inputs
  const [targetId, setTargetId] = useState<number>(targets[0]?.id || 0);
  const [generationMode, setGenerationMode] = useState<string>('RDKit_ENUMERATION');
  const [requestedCount, setRequestedCount] = useState<number>(20);
  const [randomSeed, setRandomSeed] = useState<number>(42);

  useEffect(() => {
    if (targets.length > 0 && targetId === 0) {
      setTargetId(targets[0].id);
    }
  }, [targets]);

  useEffect(() => {
    fetchRuns();
  }, [project.id]);

  const fetchRuns = async () => {
    try {
      setLoading(true);
      const data = await api.getGenerationRuns(project.id);
      setRuns(data);
      if (data.length > 0) {
        setSelectedRun(data[0]);
        fetchMolecules(data[0].id);
      } else {
        setSelectedRun(null);
        setMolecules([]);
      }
    } catch (e) {
      console.error('Error fetching generation runs:', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchMolecules = async (runId: number) => {
    try {
      const data = await api.getProjectMolecules(project.id, runId);
      setMolecules(data);
    } catch (e) {
      console.error('Error fetching molecules:', e);
    }
  };

  const handleCreateAndExecuteRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetId) {
      alert('Please select a target protein.');
      return;
    }
    try {
      setExecuting(true);
      const newRun = await api.createGenerationRun(project.id, {
        target_id: targetId,
        generation_mode: generationMode,
        requested_count: requestedCount,
        random_seed: randomSeed,
        run_name: `${generationMode} for Target #${targetId}`
      });

      const execRes = await api.executeGenerationRun(project.id, newRun.id);
      await fetchRuns();
      if (execRes.status === 'NOT_AVAILABLE') {
        alert(`Generator Not Available: ${execRes.error_message || 'Model is not installed locally.'}`);
      }
    } catch (e: any) {
      alert(`Generation failed: ${e.message}`);
    } finally {
      setExecuting(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSmiles(text);
    setTimeout(() => setCopiedSmiles(null), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-emerald-400" />
              Target-Conditioned Molecular Generation Engine
            </h2>
            <p className="text-sm text-slate-400">
              Generates and filters candidate herbicide molecules with complete scientific provenance.
            </p>
          </div>
          <button
            onClick={fetchRuns}
            className="px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>

        {/* Generation Request Form */}
        <form onSubmit={handleCreateAndExecuteRun} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 items-end">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Biological Target</label>
            <select
              value={targetId}
              onChange={(e) => setTargetId(Number(e.target.value))}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
            >
              {targets.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.uniprot_id || 'Target'})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Generation Method</label>
            <select
              value={generationMode}
              onChange={(e) => setGenerationMode(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
            >
              <option value="RDKit_ENUMERATION">RDKit Chemical Enumeration</option>
              <option value="FRAGMENT_RECOMBINATION">Fragment Recombination (BRICS)</option>
              <option value="DATABASE_RETRIEVAL">Database Retrieval (PubChem & ChEMBL)</option>
              <option value="GENERATIVE_AI_ADAPTER">Generative AI Model Adapter</option>
            </select>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-slate-400">Candidate Tier</label>
              <div className="flex gap-1 text-[10px]">
                <button type="button" onClick={() => setRequestedCount(10)} className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700">10 (Quick)</button>
                <button type="button" onClick={() => setRequestedCount(50)} className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700">50 (Std)</button>
                <button type="button" onClick={() => setRequestedCount(100)} className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700">100 (Deep)</button>
                <button type="button" onClick={() => setRequestedCount(500)} className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700">500 (Max)</button>
              </div>
            </div>
            <input
              type="number"
              min={1}
              max={500}
              value={requestedCount}
              onChange={(e) => setRequestedCount(Number(e.target.value))}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Random Seed (Reproducibility)</label>
            <input
              type="number"
              value={randomSeed}
              onChange={(e) => setRandomSeed(Number(e.target.value))}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
            />
          </div>

          <div>
            <button
              type="submit"
              disabled={executing || targets.length === 0}
              className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 text-white font-medium py-2 px-4 rounded-lg flex items-center justify-center gap-2 text-sm transition-colors"
            >
              {executing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" /> Generating...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" /> Run Generation
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Generation Runs Selector */}
      {runs.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-2">
          {runs.map((r) => (
            <button
              key={r.id}
              onClick={() => {
                setSelectedRun(r);
                fetchMolecules(r.id);
              }}
              className={`px-4 py-2 rounded-lg text-xs font-medium border text-left whitespace-nowrap transition-colors ${
                selectedRun?.id === r.id
                  ? 'bg-emerald-950/40 border-emerald-500 text-emerald-300'
                  : 'bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700'
              }`}
            >
              <div className="font-semibold text-white">{r.run_name}</div>
              <div className="flex items-center gap-2 mt-1">
                <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                  r.status === 'COMPLETED' ? 'bg-emerald-900/60 text-emerald-300' :
                  r.status === 'NOT_AVAILABLE' ? 'bg-amber-900/60 text-amber-300' : 'bg-red-900/60 text-red-300'
                }`}>
                  {r.status}
                </span>
                <span>{r.valid_count} Valid</span>
                <span>• Seed: {r.random_seed}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Selected Run Metrics */}
      {selectedRun && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="bg-slate-900 border border-slate-800 p-3 rounded-lg">
            <span className="text-xs text-slate-400">Status</span>
            <div className="text-base font-bold text-white mt-1">{selectedRun.status}</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-3 rounded-lg">
            <span className="text-xs text-slate-400">Generated</span>
            <div className="text-base font-bold text-white mt-1">{selectedRun.generated_count} / {selectedRun.requested_count}</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-3 rounded-lg">
            <span className="text-xs text-slate-400">Chemically Valid</span>
            <div className="text-base font-bold text-emerald-400 mt-1">{selectedRun.valid_count}</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-3 rounded-lg">
            <span className="text-xs text-slate-400">Rejected</span>
            <div className="text-base font-bold text-red-400 mt-1">{selectedRun.rejected_count}</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-3 rounded-lg">
            <span className="text-xs text-slate-400">Unique (InChIKey)</span>
            <div className="text-base font-bold text-sky-400 mt-1">{selectedRun.unique_count}</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-3 rounded-lg">
            <span className="text-xs text-slate-400">Novel / Low Sim</span>
            <div className="text-base font-bold text-purple-400 mt-1">{selectedRun.novel_count}</div>
          </div>
        </div>
      )}

      {/* Generated Candidates Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-slate-800 flex justify-between items-center">
          <h3 className="text-sm font-semibold text-white">Generated Molecule Candidates</h3>
          <span className="text-xs text-slate-400">{molecules.length} candidates loaded</span>
        </div>

        {molecules.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-sm">
            {loading ? 'Loading candidates...' : 'No candidate molecules generated for this run yet.'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/60 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-3 font-medium">Compound Code</th>
                  <th className="p-3 font-medium">Canonical SMILES</th>
                  <th className="p-3 font-medium">Method</th>
                  <th className="p-3 font-medium">MW</th>
                  <th className="p-3 font-medium">LogP</th>
                  <th className="p-3 font-medium">TPSA</th>
                  <th className="p-3 font-medium">Pocket Fit</th>
                  <th className="p-3 font-medium">Novelty Category</th>
                  <th className="p-3 font-medium">Alert Screen</th>
                  <th className="p-3 font-medium">Validation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {molecules.map((m) => (
                  <tr key={m.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="p-3 font-mono font-medium text-emerald-400 whitespace-nowrap">
                      {m.compound_code}
                    </td>
                    <td className="p-3 max-w-[240px]">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-slate-300 truncate" title={m.canonical_smiles || m.smiles}>
                          {m.canonical_smiles || m.smiles}
                        </span>
                        <button
                          onClick={() => copyToClipboard(m.canonical_smiles || m.smiles)}
                          className="p-1 text-slate-400 hover:text-white"
                          title="Copy SMILES"
                        >
                          {copiedSmiles === (m.canonical_smiles || m.smiles) ? (
                            <Check className="w-3 h-3 text-emerald-400" />
                          ) : (
                            <Copy className="w-3 h-3" />
                          )}
                        </button>
                      </div>
                    </td>
                    <td className="p-3 text-slate-400 whitespace-nowrap">{m.generation_mode}</td>
                    <td className="p-3 text-slate-300 whitespace-nowrap">{m.mw ? `${m.mw}` : '—'}</td>
                    <td className="p-3 text-slate-300 whitespace-nowrap">{m.logp !== undefined ? `${m.logp}` : '—'}</td>
                    <td className="p-3 text-slate-300 whitespace-nowrap">{m.tpsa ? `${m.tpsa} Å²` : '—'}</td>
                    <td className="p-3 whitespace-nowrap">
                      {m.pocket_fit_score !== undefined && m.pocket_fit_score !== null ? (
                        <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                          m.pocket_fit_score >= 0.70 ? 'bg-emerald-950 text-emerald-300' :
                          m.pocket_fit_score >= 0.50 ? 'bg-blue-950 text-blue-300' :
                          'bg-slate-800 text-slate-400'
                        }`}>
                          {(m.pocket_fit_score * 100).toFixed(0)}%
                        </span>
                      ) : (
                        <span className="text-slate-500 text-xs">—</span>
                      )}
                    </td>
                    <td className="p-3 whitespace-nowrap">
                      {m.novelty_category ? (
                        <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                          m.novelty_category === 'KNOWN_EXACT_MATCH' ? 'bg-slate-800 text-slate-300' :
                          m.novelty_category === 'HIGH_SIMILARITY' ? 'bg-amber-950 text-amber-300' :
                          m.novelty_category === 'MODERATE_SIMILARITY' ? 'bg-blue-950 text-blue-300' :
                          'bg-purple-950 text-purple-300'
                        }`}>
                          {m.novelty_category}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="p-3 whitespace-nowrap">
                      {m.structural_alerts_count > 0 ? (
                        <span className="text-amber-400 flex items-center gap-1 font-medium text-[10px]">
                          <AlertCircle className="w-3.5 h-3.5" /> {m.structural_alerts_count} alert(s)
                        </span>
                      ) : (
                        <span className="text-emerald-400 flex items-center gap-1 text-[10px]">
                          <CheckCircle2 className="w-3.5 h-3.5" /> No structural alerts detected
                        </span>
                      )}
                    </td>
                    <td className="p-3 whitespace-nowrap">
                      {m.chemical_validation_status === 'VALID' ? (
                        <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 text-[10px] font-medium">
                          VALID
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded bg-red-950 text-red-300 text-[10px] font-medium" title={m.rejection_reason || ''}>
                          REJECTED
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
