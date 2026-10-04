import React, { useEffect, useRef } from 'react';

interface ViewerProps {
  pdbId?: string;
  height?: string;
}

export const ProteinViewer3D: React.FC<ViewerProps> = ({ pdbId = "1YI2", height = "350px" }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current && (window as any).$3Dmol) {
      const element = containerRef.current;
      element.innerHTML = "";
      const config = { backgroundColor: '0x0f172a' };
      const viewer = (window as any).$3Dmol.createViewer(element, config);

      // Fetch sample PDB structure
      fetch(`https://files.rcsb.org/download/${pdbId}.pdb`)
        .then(res => res.text())
        .then(data => {
          viewer.addModel(data, "pdb");
          viewer.setStyle({}, { cartoon: { color: 'spectrum' } });
          viewer.zoomTo();
          viewer.render();
        })
        .catch(() => {
          // Fallback simple geometric representation
          viewer.addSphere({ center: { x: 0, y: 0, z: 0 }, radius: 10.0, color: 'green' });
          viewer.zoomTo();
          viewer.render();
        });
    }
  }, [pdbId]);

  return (
    <div className="relative rounded-lg overflow-hidden border border-slate-700 bg-slate-900">
      <div ref={containerRef} style={{ width: '100%', height }} />
      <div className="absolute top-2 right-2 bg-slate-800/80 backdrop-blur px-3 py-1 rounded text-xs text-slate-300 border border-slate-700">
        3Dmol.js Interactive Protein Viewer ({pdbId})
      </div>
    </div>
  );
};
