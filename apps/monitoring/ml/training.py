import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

TARGET_INDICES = None


def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class SequenceDataset(Dataset):
    def __init__(self, x: np.ndarray, y: np.ndarray):
        self.x = torch.from_numpy(x).float()
        self.y = torch.from_numpy(y).float()

    def __len__(self) -> int:
        return len(self.x)

    def __getitem__(self, idx: int):
        return self.x[idx], self.y[idx]


class Standardizer:
    def __init__(self):
        self.mean = None
        self.std = None

    def fit(self, x: np.ndarray) -> None:
        self.mean = x.mean(axis=(0, 1), keepdims=True)
        self.std = x.std(axis=(0, 1), keepdims=True)
        self.std = np.where(self.std < 1e-6, 1.0, self.std)

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / self.std

    def inverse_transform_targets(self, y: torch.Tensor, target_idx: np.ndarray) -> torch.Tensor:
        mean = torch.as_tensor(self.mean[:, :, target_idx], dtype=y.dtype, device=y.device)
        std = torch.as_tensor(self.std[:, :, target_idx], dtype=y.dtype, device=y.device)
        return y * std + mean


class AirSeq2Seq(nn.Module):
    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        horizon: int,
        hidden_dim: int = 32,
        num_layers: int = 1,
        dropout: float = 0.15,
    ):
        super().__init__()
        self.horizon = horizon
        self.output_dim = output_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.dropout = dropout

        self.encoder = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.context_norm = nn.LayerNorm(hidden_dim)
        self.decoder = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, horizon * output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, hidden = self.encoder(x)
        context = self.context_norm(hidden[-1])
        out = self.decoder(context)
        return out.view(-1, self.horizon, self.output_dim)


@dataclass
class TrainArtifacts:
    model: nn.Module
    x_scaler: Standardizer
    y_mean: np.ndarray
    y_std: np.ndarray
    history: Dict[str, list]


def compute_target_stats(y_train: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    mean = y_train.mean(axis=(0, 1), keepdims=True)
    std = y_train.std(axis=(0, 1), keepdims=True)
    std = np.where(std < 1e-6, 1.0, std)
    return mean, std


def normalize_targets(y: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return (y - mean) / std


def denormalize_targets(y: torch.Tensor, mean: np.ndarray, std: np.ndarray) -> torch.Tensor:
    mean_t = torch.as_tensor(mean, dtype=y.dtype, device=y.device)
    std_t = torch.as_tensor(std, dtype=y.dtype, device=y.device)
    return y * std_t + mean_t


def rmse_mae_per_target(
    y_true: np.ndarray, y_pred: np.ndarray, target_names: np.ndarray
) -> Dict[str, Dict[str, float]]:
    metrics: Dict[str, Dict[str, float]] = {}
    for i, name in enumerate(target_names.tolist()):
        err = y_pred[:, :, i] - y_true[:, :, i]
        rmse = float(np.sqrt(np.mean(err**2)))
        mae = float(np.mean(np.abs(err)))
        metrics[name] = {"rmse": rmse, "mae": mae}
    return metrics


def build_evaluation_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, target_names: np.ndarray
) -> Dict[str, Dict[str, float] | dict]:
    per_target: Dict[str, Dict[str, float]] = {}
    rmse_values = []
    mae_values = []
    mape_values = []
    max_abs_errors = []

    for i, name in enumerate(target_names.tolist()):
        err = y_pred[:, :, i] - y_true[:, :, i]
        abs_err = np.abs(err)
        denom = np.where(np.abs(y_true[:, :, i]) < 1e-6, np.nan, np.abs(y_true[:, :, i]))
        rmse = float(np.sqrt(np.mean(err**2)))
        mae = float(np.mean(abs_err))
        mape = float(np.nan_to_num(np.nanmean(abs_err / denom) * 100.0, nan=0.0))
        max_abs_error = float(np.max(abs_err))

        rmse_values.append(rmse)
        mae_values.append(mae)
        mape_values.append(mape)
        max_abs_errors.append(max_abs_error)
        per_target[name] = {
            "rmse": rmse,
            "mae": mae,
            "mape": mape,
            "max_abs_error": max_abs_error,
        }

    overall_err = y_pred - y_true
    summary = {
        "overall_rmse": float(np.sqrt(np.mean(overall_err**2))),
        "overall_mae": float(np.mean(np.abs(overall_err))),
        "macro_rmse": float(np.mean(rmse_values)),
        "macro_mae": float(np.mean(mae_values)),
        "macro_mape": float(np.mean(mape_values)),
        "max_abs_error": float(np.max(max_abs_errors)),
    }

    return {
        "summary": summary,
        "per_target": per_target,
    }


def train_model(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    target_names: np.ndarray,
    batch_size: int = 32,
    epochs: int = 250,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    patience: int = 25,
    device: str = "cpu",
) -> TrainArtifacts:
    x_scaler = Standardizer()
    x_scaler.fit(x_train)
    x_train_s = x_scaler.transform(x_train)
    x_val_s = x_scaler.transform(x_val)

    y_mean, y_std = compute_target_stats(y_train)
    y_train_s = normalize_targets(y_train, y_mean, y_std)
    y_val_s = normalize_targets(y_val, y_mean, y_std)

    train_loader = DataLoader(SequenceDataset(x_train_s, y_train_s), batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(SequenceDataset(x_val_s, y_val_s), batch_size=batch_size, shuffle=False)

    model = AirSeq2Seq(
        input_dim=x_train.shape[-1],
        output_dim=y_train.shape[-1],
        horizon=y_train.shape[1],
    ).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=8)
    criterion = nn.SmoothL1Loss()

    best_val = math.inf
    best_state = None
    wait = 0
    history = {"train_loss": [], "val_loss": []}

    for epoch in range(1, epochs + 1):
        model.train()
        train_losses = []
        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb = xb.to(device)
                yb = yb.to(device)
                pred = model(xb)
                val_losses.append(criterion(pred, yb).item())

        train_loss = float(np.mean(train_losses))
        val_loss = float(np.mean(val_losses))
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        scheduler.step(val_loss)

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                break

        if epoch % 10 == 0 or epoch == 1:
            print(f"epoch={epoch:03d} train_loss={train_loss:.4f} val_loss={val_loss:.4f}")

    if best_state is None:
        raise RuntimeError("Training failed: no best model state captured.")

    model.load_state_dict(best_state)
    return TrainArtifacts(model=model, x_scaler=x_scaler, y_mean=y_mean, y_std=y_std, history=history)


@torch.no_grad()
def predict(
    model: nn.Module, x: np.ndarray, x_scaler: Standardizer, y_mean: np.ndarray, y_std: np.ndarray, device: str
) -> np.ndarray:
    model.eval()
    x_s = x_scaler.transform(x)
    xb = torch.from_numpy(x_s).float().to(device)
    pred = model(xb)
    pred = denormalize_targets(pred, y_mean, y_std)
    return pred.cpu().numpy()


@torch.no_grad()
def recursive_forecast_next24(
    model: nn.Module,
    latest_window: np.ndarray,
    x_scaler: Standardizer,
    y_mean: np.ndarray,
    y_std: np.ndarray,
    feature_names: np.ndarray,
    target_names: np.ndarray,
    device: str,
) -> np.ndarray:
    """
    Возвращает прогноз на 24 часа по последнему окну 72x33.
    Предполагается, что первые признаки, совпадающие по именам с target_names,
    являются теми же загрязнителями/индексами во входе.
    Остальные признаки на горизонте копируются из последнего часа.
    """
    pred = predict(model, latest_window[None, :, :], x_scaler, y_mean, y_std, device=device)[0]

    # Ограничиваем отрицательные концентрации.
    pred = np.maximum(pred, 0.0)

    # При желании дальше можно собрать autoregressive rollout на 48/72 часа.
    return pred


def save_artifacts(
    out_dir: Path,
    artifacts: TrainArtifacts,
    feature_names: np.ndarray,
    target_names: np.ndarray,
    test_metrics: Dict[str, Dict[str, float]],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": artifacts.model.state_dict(),
            "feature_names": feature_names.tolist(),
            "target_names": target_names.tolist(),
            "x_mean": artifacts.x_scaler.mean,
            "x_std": artifacts.x_scaler.std,
            "y_mean": artifacts.y_mean,
            "y_std": artifacts.y_std,
            "model_config": {
                "input_dim": len(feature_names),
                "output_dim": len(target_names),
                "horizon": artifacts.model.horizon,
                "hidden_dim": artifacts.model.hidden_dim,
                "num_layers": artifacts.model.num_layers,
                "dropout": artifacts.model.dropout,
            },
        },
        out_dir / "air_forecaster.pt",
    )

    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(test_metrics, f, ensure_ascii=False, indent=2)

    with open(out_dir / "history.json", "w", encoding="utf-8") as f:
        json.dump(artifacts.history, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    parser.add_argument("--epochs", type=int, default=250)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    set_seed(args.seed)
    torch.set_num_threads(1)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    data = np.load(args.data, allow_pickle=True)
    x_train = data["X_train"].astype(np.float32)
    y_train = data["y_train"].astype(np.float32)
    x_val = data["X_val"].astype(np.float32)
    y_val = data["y_val"].astype(np.float32)
    x_test = data["X_test"].astype(np.float32)
    y_test = data["y_test"].astype(np.float32)
    feature_names = data["feature_names"]
    target_names = data["target_names"]

    artifacts = train_model(
        x_train=x_train,
        y_train=y_train,
        x_val=x_val,
        y_val=y_val,
        target_names=target_names,
        batch_size=args.batch_size,
        epochs=args.epochs,
        lr=args.lr,
        weight_decay=args.weight_decay,
        patience=args.patience,
        device=device,
    )

    y_pred_test = predict(artifacts.model, x_test, artifacts.x_scaler, artifacts.y_mean, artifacts.y_std, device)
    y_pred_test = np.maximum(y_pred_test, 0.0)
    metrics = rmse_mae_per_target(y_test, y_pred_test, target_names)

    print("\nTest metrics:")
    for name, vals in metrics.items():
        print(f"{name:20s} RMSE={vals['rmse']:.3f}  MAE={vals['mae']:.3f}")

    latest_pred = recursive_forecast_next24(
        model=artifacts.model,
        latest_window=x_test[-1],
        x_scaler=artifacts.x_scaler,
        y_mean=artifacts.y_mean,
        y_std=artifacts.y_std,
        feature_names=feature_names,
        target_names=target_names,
        device=device,
    )
    print("\nLast-window next-24h forecast shape:", latest_pred.shape)

    save_artifacts(args.out, artifacts, feature_names, target_names, metrics)


if __name__ == "__main__":
    main()
