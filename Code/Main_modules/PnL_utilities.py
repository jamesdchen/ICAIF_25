import torch
from kmeans_pytorch import kmeans


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def sqrtinvdiag(M):
    return torch.diag(1.0 / torch.max(torch.sqrt(torch.diag(M)), torch.tensor(1e-10)))

def spectral_clustering_laplacian(p, n, k):
    D_p = torch.diag(p.sum(axis=0))
    D_n = torch.diag(n.sum(axis=0))
    d = sqrtinvdiag(D_p)
    matrix = d @ p @ d
    d = sqrtinvdiag(D_n)
    matrix = matrix - (d @ n @ d)
    matrix = torch.eye(matrix.shape[0], device=device) - matrix
    w, v = torch.linalg.eigh(matrix)
    # u = v[:, :k]
    # # normalize the rows to have unit 2-norm
    # t = u / u.norm(dim=1, keepdim=True)
    return kmeans(v/w, k, device=device)

def SPONGE(p, n, k, tau):
    D_p = torch.diag(p.sum(axis=0))
    D_n = torch.diag(n.sum(axis=0))

def calculate_pnl_torch(forecast_tensor, actual_tensor):
    # Removed empty tensor checks and inconsistent shape checks
    min_len = min(forecast_tensor.shape[0], actual_tensor.shape[0])
    common_series = min(forecast_tensor.shape[1], actual_tensor.shape[1])

    forecast_aligned = forecast_tensor[:min_len, :common_series]
    actual_aligned = actual_tensor[:min_len, :common_series]

    positions = torch.sign(forecast_aligned)
    pnl_per_period = positions * actual_aligned
    return pnl_per_period.sum(dim=0)

def _calculate_correlation_matrix_functional(asset_returns_lookback_tensor, device_param=None):
    # derived_device = device_param if device_param is not None else asset_returns_lookback_tensor.device
    # derived_dtype = asset_returns_lookback_tensor.dtype

    # Removed empty/small tensor check
    corr_matrix = torch.corrcoef(asset_returns_lookback_tensor.T)
    # Removed torch.nan_to_num
    return corr_matrix

def _apply_clustering_algorithm_functional(correlation_matrix_tensor, num_clusters_to_form, cluster_method, device_param=None):
    derived_device = device_param if device_param is not None else correlation_matrix_tensor.device
    num_assets = correlation_matrix_tensor.shape[0]

    # Removed num_assets == 0 check
    effective_n_clusters = min(num_clusters_to_form, num_assets)
    # Removed effective_n_clusters <= 0 check (it will use original num_clusters_to_form if < min result or proceed if min result is <=0)


    if cluster_method == 'spectral_clustering':
        pos_corr = torch.clamp(correlation_matrix_tensor, min=0)
        neg_corr = torch.abs(torch.clamp(correlation_matrix_tensor, max=0))
        labels, _ = spectral_clustering_laplacian(pos_corr, neg_corr, effective_n_clusters)
    else:
        raise ValueError(f"Unsupported cluster_method: {cluster_method}")
    return labels.to(derived_device)

def _define_clusters_and_centroids_functional(asset_returns_lookback_tensor, initial_n_clusters_config, cluster_method, device_param=None):
    derived_device = device_param if device_param is not None else asset_returns_lookback_tensor.device

    asset_corr_matrix = _calculate_correlation_matrix_functional(asset_returns_lookback_tensor, derived_device)
    # num_assets = asset_corr_matrix.shape[0] # Not strictly needed after removing checks

    cluster_definitions = {}
    cluster_names_ordered = []
    # actual_n_clusters_formed = 0 # Calculated later

    output_corr_matrix = asset_corr_matrix # Default, may be overwritten

    # Removed num_assets == 0 check

    labels = _apply_clustering_algorithm_functional(asset_corr_matrix, initial_n_clusters_config, cluster_method, derived_device)
    # def handmade_unique(x):
    #   sorted_x, _ = torch.sort(x)
    #   mask = (sorted_x[1:] - sorted_x[:-1])>0
    #   return sorted_x[1:]*mask
    # unique_labels = handmade_unique(labels).nonzero_static(size = )[0]
    # unique_labels = torch.nonzero(unique_labels, as_tuple=False).squeeze()
    # print(unique_labels)

    centroids_to_cat = []
    cluster_names = []

    for label_val_tensor in torch.arange(initial_n_clusters_config):
        cluster_name = label_val_tensor + 1
        cluster_names.append(cluster_name)
        asset_indices_in_cluster = (labels == label_val_tensor).nonzero_static(size = labels.shape[0])[0]

        centroid_ts = asset_returns_lookback_tensor[:, asset_indices_in_cluster].mean(dim=1)
        cluster_definitions[cluster_name] = {
            'asset_indices': asset_indices_in_cluster,
            'centroid_ts': centroid_ts
        }
        centroids_to_cat.append(centroid_ts.unsqueeze(0))

    # Removed 'if centroids_to_cat:' check
    all_centroids_stacked = torch.cat(centroids_to_cat, dim=0)
    # Removed shape check for all_centroids_stacked before corrcoef
    output_corr_matrix = torch.corrcoef(all_centroids_stacked)
    # Removed torch.nan_to_num

    return cluster_definitions, cluster_names, initial_n_clusters_config, output_corr_matrix

# --- REFACTORED FUNCTION for calculating weighted cluster returns ---
def _calculate_weighted_cluster_returns_functional(
    data_slice_for_returns_calc,
    data_slice_for_centroid_weights_calc,
    cluster_definitions,
    cluster_names_ordered,
    sigma_for_weights
):
    device = data_slice_for_returns_calc.device
    dtype_returns = data_slice_for_returns_calc.dtype
    dtype_weights_data = data_slice_for_centroid_weights_calc.dtype

    # Removed 'if not cluster_definitions:' and 'if not cluster_names_ordered:' checks

    T_current_period = data_slice_for_returns_calc.shape[0]
    cluster_returns_list = []

    for cluster_name in cluster_names_ordered:
        info = cluster_definitions[cluster_name] # Direct access, removed .get and None check

        asset_indices_in_cluster = info['asset_indices']
        centroid_lookback_ts = info['centroid_ts']

        current_cluster_period_returns = torch.zeros(T_current_period, device=device, dtype=dtype_returns) # Default

        # Removed 'if len(asset_indices_in_cluster) > 0:'
        asset_gaussian_weights = torch.zeros(len(asset_indices_in_cluster), device=device, dtype=dtype_weights_data) # Default

        # Removed 'if len(centroid_lookback_ts) > 0' part, kept alignment check
        if data_slice_for_centroid_weights_calc.shape[0] == len(centroid_lookback_ts):
            assets_in_cluster_returns_centroid_def_period = data_slice_for_centroid_weights_calc.index_select(1, asset_indices_in_cluster)
            centroid_lookback_ts_casted = centroid_lookback_ts.to(dtype_weights_data)

            squared_distances = torch.sum((assets_in_cluster_returns_centroid_def_period - centroid_lookback_ts_casted.unsqueeze(1))**2, dim=0)
            weights = torch.exp(-squared_distances / (2 * (sigma_for_weights**2))) # Removed + 1e-12
            asset_gaussian_weights = weights

        total_gaussian_weight_sum = asset_gaussian_weights.sum()
        assets_in_cluster_current_period = data_slice_for_returns_calc.index_select(1, asset_indices_in_cluster)

        normalized_weights = asset_gaussian_weights / total_gaussian_weight_sum # May produce NaN/inf if sum is 0
        current_cluster_period_returns = (assets_in_cluster_current_period * normalized_weights.unsqueeze(0)).sum(dim=1)

        # Removed T_current_period == 0 check for specific return shape

        cluster_returns_list.append(current_cluster_period_returns)

    # Removed 'if not cluster_returns_list:' check
    return torch.stack(cluster_returns_list, dim=1)

def _fit_var_and_forecast_functional(
    lookback_series_tensor,
    n_series_for_var_model,
    var_order, forecast_horizon, device_param=None
):
    # derived_device = device_param if device_param is not None else lookback_series_tensor.device # Not used
    model = VAR(var_order)

    model.fit(lookback_series_tensor) # Use the passed var_order

    # Convert forecast back to tensor and move to original device
    forecast_tensor_batched = model.forecast(lookback_series_tensor[-var_order:], forecast_horizon)

    return forecast_tensor_batched # (Horizon, N_series_var_model)

def _pad_tensor_cols_functional(tensor, target_cols, current_rows_for_empty_case):
    output_dtype = tensor.dtype
    # Removed tensor.numel() == 0 check and its specific return for (num_rows, target_cols)

    current_cols = tensor.shape[1]
    if current_cols == target_cols:
        return tensor
    elif current_cols < target_cols:
        padding_shape = (tensor.shape[0], target_cols - current_cols)
        # Removed handling for padding_shape[0] == 0
        padding = torch.zeros(padding_shape, device=tensor.device, dtype=output_dtype)
        return torch.cat([tensor, padding], dim=1)
    else: # current_cols > target_cols (truncate)
        return tensor[:, :target_cols]



class VAR:
    """
    Vector Autoregression (VAR) model estimated using OLS on Yule-Walker equations.
    This implementation does not use nn.Module.

    The VAR(p) model is defined as:
    y_t = c + A_1 y_{t-1} + ... + A_p y_{t-p} + u_t
    where y_t is a k-dimensional vector of variables,
    c is a k-dimensional intercept vector,
    A_i are k x k coefficient matrices,
    u_t is a k-dimensional white noise vector with covariance matrix Sigma_u.

    Estimation follows the Yule-Walker method:
    1. Estimate mean and autocovariance matrices (Gamma_j) from data.
    2. Solve the Yule-Walker equations for A_i coefficients.
       The system solved is effectively:
       Gamma_cap @ [A_1, ..., A_p].T = [Gamma_1, ..., Gamma_p].T (transposed)
       where Gamma_cap is a block matrix of autocovariances, and the solution
       for [A_1.T, ..., A_p.T].T is found using least squares (lstsq).
    3. Estimate intercept c.
    4. Estimate residual covariance Sigma_u.
    """

    def __init__(self, lag_order: int, include_intercept: bool = True):
        if lag_order < 1:
            raise ValueError("Lag order must be at least 1.")
        self.lag_order = lag_order
        self.include_intercept = include_intercept

        self.k_ = None  # Number of variables
        self.intercept_ = None  # Intercept vector c (1 x k)
        self.lag_coef_ = None  # Stacked A_i' matrices (kp x k): [A_1.T, A_2.T, ..., A_p.T].T
                               # So, A_i = self.lag_coef_[(i-1)*k : i*k, :].T
        self.sigma_u_ = None  # Residual covariance matrix (k x k)
        self.fitted_ = False
        self.mu_ = None # Mean of the series used for fitting

    def _compute_autocov(self, X_processed: torch.Tensor, lag: int) -> torch.Tensor:
        """
        Computes sample autocovariance matrix Gamma_lag.
        X_processed: (T x k) tensor, already mean-centered if intercept is included.
        lag: integer lag.
        Returns: (k x k) covariance matrix.
        Uses divisor T. For YW, sample autocovariances are often E[(y_t-mu)(y_{t-h}-mu)'].
        The divisor T is common for Gamma_0 in some contexts, and T-h for Gamma_h.
        Using T for all for consistency in constructing the YW system is one approach.
        Statsmodels VAR uses T-p for OLS and T for YW Gamma matrix elements.
        Here, we use T for simplicity, recognizing it's one common definition.
        """
        T, k = X_processed.shape
        if T <= lag:
             # This can happen if T is very small relative to p.
             # The calling fit method should check T > p.
             # For autocov computation specifically, if lag >= T, result is ill-defined or zero.
            return torch.zeros((k,k), device=X_processed.device, dtype=X_processed.dtype)


        if lag == 0:
            # Gamma_0 = (1/T) * sum_{t=1 to T} (x_t - mu)(x_t - mu)'
            return (X_processed.T @ X_processed) / T
        else:
            # Gamma_lag = (1/T) * sum_{t=lag+1 to T} (x_t - mu)(x_{t-lag} - mu)'
            # X_processed[lag:] corresponds to x_t
            # X_processed[:-lag] corresponds to x_{t-lag}
            # For (T x k) matrices, (A.T @ B) / N gives sum of (a_t' b_t) / N if a_t,b_t are columns
            # Here, X_processed[lag:] are rows for y_t, X_processed[:-lag] are rows for y_{t-lag}
            # We need sum (y_t - mu)' (y_{t-lag} - mu) if y are columns
            # (X_processed[lag:].T @ X_processed[:-lag]) gives sum_t (y_t-mu)(y_{t-lag}-mu)'
            # where (y_t-mu) is a column vector (k x 1)
            # No, it's sum_t (y_t-mu) (y_{t-lag}-mu)' where (y_t-mu) is taken as a column vector.
            # X_processed is (N_eff x k). X_processed[lag:].T is (k x (T-lag))
            # X_processed[:-lag] is ((T-lag) x k)
            # So (X_processed[lag:].T @ X_processed[:-lag]) is (k x k)
            return (X_processed[lag:].T @ X_processed[:-lag]) / T


    def fit(self, data: torch.Tensor):
        """
        Fits the VAR(p) model to the data using Yule-Walker equations.

        Args:
            data (torch.Tensor): Time series data of shape (T x k),
                                 where T is the number of observations and
                                 k is the number of variables.
        """
        T, k = data.shape
        if T <= self.lag_order:
            raise ValueError(f"Number of observations (T={T}) must be greater than lag order (p={self.lag_order}).")

        self.k_ = k
        p = self.lag_order

        device = data.device
        dtype = data.dtype

        if self.include_intercept:
            self.mu_ = data.mean(dim=0, keepdim=True)  # Shape (1 x k)
            X_processed = data - self.mu_
        else:
            self.mu_ = torch.zeros((1, k), device=device, dtype=dtype) # Assume mean zero
            X_processed = data # Data is used as is

        # 1. Estimate autocovariance matrices Gamma_j
        # We need Gamma_0, Gamma_1, ..., Gamma_p
        gammas = [self._compute_autocov(X_processed, j) for j in range(p + 1)]

        # 2. Solve Yule-Walker equations for lag coefficients (A_i)
        # System based on Lütkepohl (2005), "New Introduction to Multiple Time Series Analysis", p.70 eq (3.2.2)
        # [A_1, ..., A_p] = [Gamma_1, ..., Gamma_p] @ inv(Gamma_cap)
        # where Gamma_cap (kp x kp) is block matrix: Gamma_cap[r,c] = Gamma_{r-c} (using Gamma_{-s} = Gamma_s.T)
        # Let A_coeffs_stacked = [A_1.T, ..., A_p.T].T (kp x k)
        # Then (Gamma_cap).T @ A_coeffs_stacked = [Gamma_1.T, ..., Gamma_p.T].T

        # Construct Gamma_cap (Lütkepohl's Gamma, often denoted Psi or Big_Gamma in other texts)
        # Gamma_cap[block_row_idx, block_col_idx] = Gamma_{block_row_idx - block_col_idx}

        block_rows_list = []
        for r_idx in range(p):  # For each block row (0 to p-1)
            current_block_row_elements = []
            for c_idx in range(p):  # For each block in that row (0 to p-1)
                lag_val = r_idx - c_idx
                if lag_val == 0:
                    block_to_add = gammas[0]                            # Gamma_0
                elif lag_val > 0:
                    block_to_add = gammas[lag_val]                      # Gamma_{lag_val}
                else:  # lag_val < 0
                    block_to_add = gammas[abs(lag_val)].T               # Gamma_{-abs(lag_val)} = Gamma_{abs(lag_val)}.T
                current_block_row_elements.append(block_to_add)

            # Concatenate blocks horizontally for this block row
            # Each element is k x k, so result is k x (p*k)
            block_row = torch.cat(current_block_row_elements, dim=1)
            block_rows_list.append(block_row)

        # Concatenate block rows vertically
        # Each block_row is k x (p*k), stacking p of them gives (p*k) x (p*k)
        gamma_cap = torch.cat(block_rows_list, dim=0)

        # Construct RHS vector: [Gamma_1.T, ..., Gamma_p.T].T (stacked vertically)
        # Each Gamma_j.T is (k x k). Stacking p of them vertically results in (pk x k)
        rhs_stacked_T_list = [gammas[j+1].T for j in range(p)] # gammas[1].T, ..., gammas[p].T
        rhs_stacked_T = torch.cat(rhs_stacked_T_list, dim=0)


        # Solve (Gamma_cap).T @ A_coeffs_stacked = rhs_stacked_T for A_coeffs_stacked
        # A_coeffs_stacked is self.lag_coef_
        try:
            # Using lstsq aligns with "OLS on Yule-Walker" by finding the least squares solution.
            self.lag_coef_ = torch.linalg.lstsq(gamma_cap.T, rhs_stacked_T).solution
        except torch.linalg.LinAlgError as e:
            raise RuntimeError(f"Failed to solve Yule-Walker system using lstsq. Matrix may be singular. Original error: {e}")


        # 3. Estimate intercept c
        if self.include_intercept:
            # c = (I - A_1 - ... - A_p) @ mu
            A_sum = torch.zeros((k, k), device=device, dtype=dtype)
            if p > 0:
                for i in range(p):
                  A_i_plus_1_T = self.lag_coef_[i * k:(i + 1) * k, :] # This is A_{i+1}.T
                  A_sum = A_sum + A_i_plus_1_T.T # This is A_{i+1}

            identity_k = torch.eye(k, device=device, dtype=dtype)
            self.intercept_ = ((identity_k - A_sum) @ self.mu_.T).T # Shape (1 x k)
        else:
            self.intercept_ = torch.zeros((1, k), device=device, dtype=dtype)

        # 4. Estimate residual covariance Sigma_u
        # Sigma_u = Gamma_0 - Sum_{j=1 to p} A_j @ Gamma_j.T (Lütkepohl eq 2.1.19)
        # Note: Lütkepohl has Gamma_j in his formula, meaning E[y_t y_{t-j}'].
        # Our Gamma_j means E[y_t y_{t-j}']. So Gamma_j.T is E[y_{t-j} y_t'].
        # Lütkepohl (3.2.5) for Sigma_u: Gamma_0 - [A_1 ... A_p] @ [Gamma_1 ... Gamma_p].T
        # Which is Gamma_0 - sum A_i Gamma_i.T
        # This is equivalent to Gamma_0 - sum A_i Gamma_{-i} (using Gamma_{-i} = Gamma_i.T)

        self.sigma_u_ = gammas[0].clone()
        if p > 0:
            for i in range(p): # i from 0 to p-1
                # A_{i+1} corresponds to the i-th block in lag_coef_
                A_i_plus_1_T = self.lag_coef_[i * k:(i + 1) * k, :] # A_{i+1}.T
                A_i_plus_1 = A_i_plus_1_T.T # A_{i+1}

                # We need A_{i+1} @ Gamma_{i+1}.T
                self.sigma_u_ -= A_i_plus_1 @ gammas[i+1].T

        self.fitted_ = True

    def _check_fitted(self):
        if not self.fitted_:
            raise RuntimeError("Model has not been fitted yet. Call fit() first.")

    def predict(self, y_init_lags, n_ahead:int):
        """
        Predicts future values of the time series.

        Args:
            y_init_lags (torch.Tensor): Initial lag values of shape (L x k) where L >= p.
                                      These are the most recent p observations, ordered
                                      chronologically (oldest to newest).
                                      Example: If p=2, y_init_lags should be [y_{t-p}; ... ; y_{t-1}].
            n_ahead (int): Number of steps to predict ahead.

        Returns:
            torch.Tensor: Predicted values of shape (n_ahead x k).
        """
        self._check_fitted()
        if y_init_lags.shape[1] != self.k_:
            raise ValueError(
                f"Initial lags have {y_init_lags.shape[1]} variables, "
                f"but model was fitted on {self.k_} variables."
            )

        p = self.lag_order
        k = self.k_

        # At this point, p > 0 and n_ahead > 0.
        if y_init_lags.shape[0] < p:
            raise ValueError(
                f"Need at least {self.lag_order} initial lags for prediction, got {y_init_lags.shape[0]}."
            )

        current_lags = y_init_lags[-p:].clone() # Shape (p x k), [y_{t-(p-1)}, ..., y_{t}] (oldest to newest)
                                                # Or, using t as 'now': [y_{t-p+1}, ..., y_t]
                                                # Or, to match Lütkepohl: [y_{t-p}, ..., y_{t-1}] used to predict y_t
                                                # The indexing current_lags[-(j+1)] handles this correctly.

        predictions_list = []

        # Use _n_ahead_val in the range function
        for _ in range(n_ahead):
            pred_row = self.intercept_.clone()

            for j in range(p):
                lagged_y_val_row_vec = current_lags[-(j + 1), :].reshape(1, k)
                A_j_plus_1_T = self.lag_coef_[j * k:(j + 1) * k, :]
                A_j_plus_1 = A_j_plus_1_T.T
                pred_row += lagged_y_val_row_vec @ A_j_plus_1

            predictions_list.append(pred_row)

            if p > 1:
                current_lags = torch.roll(current_lags, shifts=-1, dims=0)
            current_lags[-1, :] = pred_row

        return torch.cat(predictions_list, dim=0)

    def forecast(self, y_init_lags: torch.Tensor, steps: int) -> torch.Tensor:
        return self.predict(y_init_lags, steps)

    def get_params(self) -> dict:
        """Returns the estimated parameters."""
        self._check_fitted()
        return {
            "intercept": self.intercept_.clone() if self.intercept_ is not None else None,
            "lag_coefficients_stacked_T": self.lag_coef_.clone() if self.lag_coef_ is not None else None, # Stacked A_i.T (kp x k)
            "sigma_u": self.sigma_u_.clone() if self.sigma_u_ is not None else None
        }

    def get_individual_A_matrices(self) -> list:
        """Returns a list of A_i matrices [A_1, A_2, ..., A_p]."""
        self._check_fitted()
        if self.lag_order == 0:
            return []

        A_matrices = []
        for i in range(self.lag_order):
            # self.lag_coef_ stores A_{idx+1}.T at block idx
            A_i_plus_1_T = self.lag_coef_[i * self.k_ : (i + 1) * self.k_, :]
            A_matrices.append(A_i_plus_1_T.T.clone()) # A_i = (A_i.T).T
        return A_matrices