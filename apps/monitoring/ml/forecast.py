from io import BytesIO

import numpy as np
import torch

from .training import AirSeq2Seq


class AirForecaster:
    def __init__(self, *, checkpoint_blob: bytes, device: str = "cpu"):
        self.device = device
        checkpoint = torch.load(BytesIO(checkpoint_blob), map_location=device, weights_only=False)

        self.feature_names = checkpoint["feature_names"]
        self.target_names = checkpoint["target_names"]

        self.x_mean = checkpoint["x_mean"]
        self.x_std = checkpoint["x_std"]
        self.y_mean = checkpoint["y_mean"]
        self.y_std = checkpoint["y_std"]

        model_config = checkpoint.get("model_config") or {}
        input_dim = model_config.get("input_dim", len(self.feature_names))
        output_dim = model_config.get("output_dim", len(self.target_names))
        horizon = model_config.get("horizon", 24)
        hidden_dim = model_config.get("hidden_dim", 32)
        num_layers = model_config.get("num_layers", 1)
        dropout = model_config.get("dropout", 0.15)

        self.model = AirSeq2Seq(
            input_dim=input_dim,
            output_dim=output_dim,
            horizon=horizon,
            hidden_dim=hidden_dim,
            num_layers=num_layers,
            dropout=dropout,
        ).to(device)

        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()

    @torch.no_grad()
    def predict_next24(self, latest_window: np.ndarray) -> np.ndarray:
        x = (latest_window - self.x_mean[0]) / self.x_std[0]
        xb = torch.from_numpy(x[None, :, :]).float().to(self.device)

        pred = self.model(xb)
        pred = pred.cpu().numpy()[0]
        pred = pred * self.y_std[0, 0] + self.y_mean[0, 0]
        pred = np.maximum(pred, 0.0)
        return pred
