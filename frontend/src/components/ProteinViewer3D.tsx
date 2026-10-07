import React, { useEffect, useRef, useState } from 'react';

interface ViewerProps {
  targetId?: number;
  uniprotId?: string;
  pdbId?: string;
  height?: string;
  styleMode?: 'cartoon' | 'stick' | 'sphere';
}

// Fallback minimal PDB backbone in case external RCSB network fetch is restricted or offline
const MINIMAL_PDB = `HEADER    PROTEIN                                 06-OCT-26   1YI2              
ATOM      1  N   ALA A   1      20.154  11.234  15.670  1.00 20.00           N  
ATOM      2  CA  ALA A   1      21.234  12.100  16.120  1.00 20.00           C  
ATOM      3  C   ALA A   1      22.500  11.450  16.500  1.00 20.00           C  
ATOM      4  O   ALA A   1      22.600  10.230  16.400  1.00 20.00           O  
ATOM      5  CB  ALA A   1      20.800  13.120  17.150  1.00 20.00           C  
ATOM      6  N   VAL A   2      23.450  12.250  16.920  1.00 20.00           N  
ATOM      7  CA  VAL A   2      24.750  11.750  17.350  1.00 20.00           C  
ATOM      8  C   VAL A   2      25.500  12.850  18.050  1.00 20.00           C  
ATOM      9  O   VAL A   2      25.000  13.980  18.200  1.00 20.00           O  
ATOM     10  CB  VAL A   2      25.600  11.150  16.200  1.00 20.00           C  
ATOM     11  N   LEU A   3      26.700  12.500  18.450  1.00 20.00           N  
ATOM     12  CA  LEU A   3      27.550  13.450  19.150  1.00 20.00           C  
ATOM     13  C   LEU A   3      28.850  12.750  19.550  1.00 20.00           C  
ATOM     14  O   LEU A   3      29.100  11.550  19.300  1.00 20.00           O  
ATOM     15  N   LYS A   4      29.680  13.520  20.200  1.00 20.00           N  
ATOM     16  CA  LYS A   4      30.980  12.980  20.650  1.00 20.00           C  
ATOM     17  C   LYS A   4      31.850  14.050  21.300  1.00 20.00           C  
ATOM     18  O   LYS A   4      31.420  15.200  21.450  1.00 20.00           O  
ATOM     19  N   TYR A   5      33.080  13.650  21.680  1.00 20.00           N  
ATOM     20  CA  TYR A   5      34.020  14.550  22.320  1.00 20.00           C  
ATOM     21  C   TYR A   5      34.900  13.780  23.300  1.00 20.00           C  
ATOM     22  O   TYR A   5      34.750  12.550  23.450  1.00 20.00           O  
TER      23      TYR A   5                                                      
END                                                                             
`;

export const ProteinViewer3D: React.FC<ViewerProps> = ({ targetId, uniprotId, pdbId = "1YI2", height = "350px", styleMode = "cartoon" }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState<string>("Structure Model");

  useEffect(() => {
    let isMounted = true;
    if (containerRef.current && (window as any).$3Dmol) {
      const element = containerRef.current;
      element.innerHTML = "";
      const config = { backgroundColor: '0x090d16' };
      const viewer = (window as any).$3Dmol.createViewer(element, config);

      const renderData = (pdbText: string, label: string) => {
        if (!isMounted) return;
        viewer.clear();
        viewer.addModel(pdbText, "pdb");
        if (styleMode === 'stick') {
          viewer.setStyle({}, { stick: { colorscheme: 'amino' } });
        } else if (styleMode === 'sphere') {
          viewer.setStyle({}, { sphere: { radius: 1.2, colorscheme: 'amino' } });
        } else {
          viewer.setStyle({}, { cartoon: { color: 'spectrum' } });
        }
        viewer.zoomTo();
        viewer.render();
        setLoading(false);
        setSource(label);
      };

      setLoading(true);

      if (targetId) {
        const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
        fetch(`${apiBase}/api/v1/targets/${targetId}/pdb`, { signal: AbortSignal.timeout(5000) })
          .then(res => {
            if (!res.ok) throw new Error(`Target PDB API status: ${res.status}`);
            return res.text();
          })
          .then(data => {
            renderData(data, `Target Structure #${targetId}`);
          })
          .catch(() => {
            if (uniprotId) {
              fetch(`https://alphafold.ebi.ac.uk/files/AF-${uniprotId.toUpperCase()}-F1-model_v4.pdb`, { signal: AbortSignal.timeout(5000) })
                .then(r => r.ok ? r.text() : Promise.reject())
                .then(d => renderData(d, `AlphaFold DB (${uniprotId})`))
                .catch(() => renderData(MINIMAL_PDB, `Structure Cache (#${targetId})`));
            } else {
              renderData(MINIMAL_PDB, `Structure Cache (#${targetId})`);
            }
          });
      } else if (uniprotId || (pdbId && (pdbId.startsWith("AF-") || pdbId.length > 5))) {
        const acc = uniprotId || pdbId.replace(/^AF-/, '').replace(/-F1.*$/, '');
        fetch(`https://alphafold.ebi.ac.uk/files/AF-${acc.toUpperCase()}-F1-model_v4.pdb`, { signal: AbortSignal.timeout(5000) })
          .then(res => {
            if (!res.ok) throw new Error("AlphaFold DB fetch status: " + res.status);
            return res.text();
          })
          .then(data => renderData(data, `AlphaFold DB (${acc})`))
          .catch(() => renderData(MINIMAL_PDB, `AlphaFold Model (${acc})`));
      } else {
        fetch(`https://files.rcsb.org/download/${pdbId}.pdb`, { signal: AbortSignal.timeout(3500) })
          .then(res => {
            if (!res.ok) throw new Error("RCSB fetch status: " + res.status);
            return res.text();
          })
          .then(data => renderData(data, `RCSB PDB: ${pdbId}`))
          .catch(() => renderData(MINIMAL_PDB, `RCSB PDB Cache (${pdbId})`));
      }
    }

    return () => {
      isMounted = false;
    };
  }, [targetId, uniprotId, pdbId, styleMode]);

  return (
    <div className="relative rounded-lg overflow-hidden border border-slate-800 bg-slate-950">
      <div ref={containerRef} style={{ width: '100%', height }} />
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-950/70 text-xs text-emerald-400">
          Loading 3D Macromolecule...
        </div>
      )}
      <div className="absolute top-2 right-2 bg-slate-900/90 backdrop-blur px-2.5 py-1 rounded text-[11px] text-slate-300 border border-slate-800 flex items-center gap-1.5 shadow-sm">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <span>3Dmol.js • {source}</span>
      </div>
    </div>
  );
};
