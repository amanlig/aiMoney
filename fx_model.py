"""Investment-side adapter for the independent CIBC FX model implementation."""
import importlib.util
from pathlib import Path

MODEL_DIR=Path(__file__).resolve().parents[1]/'models/financials/cibc_fx'
_spec=importlib.util.spec_from_file_location('_investment_cibc_fx_model',MODEL_DIR/'model.py')
_module=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
predict=_module.predict
