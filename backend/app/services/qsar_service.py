import numpy as np
from typing import Dict, Any, List
from rdkit import Chem
from rdkit.Chem import AllChem
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_squared_error

class QSARActiveLearningEngine:
    """Trains QSAR models on real experimental data and performs active learning uncertainty sampling with zero fake data."""

    def __init__(self):
        self.model = RandomForestRegressor(n_estimators=50, random_state=42)
        self.is_trained = False

    def _smiles_to_fp(self, smiles: str):
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return np.zeros((2048,))
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        arr = np.zeros((0,), dtype=int)
        Chem.DataStructs.ConvertToNumpyArray(fp, arr)
        return arr

    def train_qsar(self, smiles_list: List[str], activity_list: List[float]) -> Dict[str, Any]:
        if not smiles_list or len(smiles_list) < 3:
            return {
                "status": "INSUFFICIENT_DATA",
                "sample_count": len(smiles_list) if smiles_list else 0,
                "message": "At least 3 valid experimental observations are required to train QSAR model."
            }

        X = np.array([self._smiles_to_fp(s) for s in smiles_list])
        y = np.array(activity_list)

        self.model.fit(X, y)
        self.is_trained = True

        y_pred = self.model.predict(X)
        r2 = float(r2_score(y, y_pred)) if len(y) > 1 else 1.0
        rmse = float(np.sqrt(mean_squared_error(y, y_pred)))

        return {
            "status": "TRAINED",
            "model_type": "RandomForestRegressor (Morgan FP)",
            "sample_count": len(smiles_list),
            "r2_score": round(r2, 3),
            "rmse": round(rmse, 3)
        }

    def predict_with_uncertainty(self, candidate_smiles: List[str]) -> List[Dict[str, Any]]:
        """Predicts activity and uncertainty (std dev across trees in RF) for active learning prioritization."""
        if not self.is_trained:
            return [
                {
                    "smiles": s,
                    "predicted_activity_pct": None,
                    "uncertainty_std": None,
                    "active_learning_priority": "REQUIRES_EXPERIMENTAL_QSAR_TRAINING",
                    "status": "UNPOWERED_MODEL_NOT_TRAINED"
                }
                for s in candidate_smiles
            ]

        X = np.array([self._smiles_to_fp(s) for s in candidate_smiles])

        tree_preds = np.array([tree.predict(X) for tree in self.model.estimators_])
        mean_preds = np.mean(tree_preds, axis=0)
        std_preds = np.std(tree_preds, axis=0)

        results = []
        for i, s in enumerate(candidate_smiles):
            results.append({
                "smiles": s,
                "predicted_activity_pct": round(float(mean_preds[i]), 2),
                "uncertainty_std": round(float(std_preds[i]), 2),
                "active_learning_priority": "HIGH_INFORMATIONAL_VALUE" if std_preds[i] > 10.0 else "STANDARD",
                "status": "COMPLETED"
            })
        return results
