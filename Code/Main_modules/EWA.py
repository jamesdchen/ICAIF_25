import pandas as pd
import numpy as np 
from sklearn.model_selection import ShuffleSplit
import sys 

np.set_printoptions(precision=10)

# ----------------------------------------------------------------

try:

    from tqdm import tqdm

except ImportError:

    print("PyPortfolioOpt package not found. Installing...")

    try:

        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
        from tqdm import tqdm
        
    except Exception as e:
        print(f"Error installing tqdm package: {e}")
        sys.exit(1)

# ----------------------------------------------------------------

# ----------------------------------------------------------------

try:

    from pypfopt.efficient_frontier import EfficientFrontier

except ImportError:

    print("PyPortfolioOpt package not found. Installing...")

    try:

        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "PyPortfolioOpt"])
        from pypfopt.efficient_frontier import EfficientFrontier
        
    except Exception as e:
        print(f"Error installing PyPortfolioOpt package: {e}")
        sys.exit(1)

# ----------------------------------------------------------------

###########################################################################################################################
###########################################################################################################################
#################################################### EWA STRAT ############################################################
###########################################################################################################################
###########################################################################################################################
        
######################### 1. We start by randomizing the auxiliary observation matrix  ̃X from Equation (5) along the time axis #########################
def EWA(beta, data, lookback_window):

    '''
    ----------------------------------------------------------------
    GENERAL IDEA : compute the auxiliary matrix associated with a
                    matrix of observations in order to later 
                    compute the EMA-SC.
    ----------------------------------------------------------------

    ----------------------------------------------------------------
    PARAMS : 

    - beta : float in (0, 1) called the exponential decay rate

    - lookback_window : list of length 2, [start, end] corresponding 
                        to the range of the lookback_window
    
    - data : matrix of observations of shape (d, n) where d is the 
                number of days observed and n is the number of assets
                that compose our portfolio
    ----------------------------------------------------------------

    ----------------------------------------------------------------
    OUTPUT : output the auxiliary matrix as defined in the paper
    ----------------------------------------------------------------
    '''

    X = data.iloc[lookback_window[0]:lookback_window[1], :]

    ## 1. We extract the data corresponding to the returns of our assets (columns) during these d days (lines)
    days = lookback_window[1]-lookback_window[0] ## shape days * number of stocks

    ## 2. We slightly adjust the matrix of observations to get the auxiliary matrix that puts more weight on recent dates

    # Compute the weight matrix : shape (days, days) (if days = 250, shape (250, 250))
    W = np.sqrt(days * ((1 - beta)/(1 - beta**days)) * np.diag(beta**(np.arange(lookback_window[0], lookback_window[1])[::-1]) / (1 - beta**days)))
    X_tilde = pd.DataFrame(index=X.index, columns=X.columns, data=np.dot(W, X))

    ## 3. We randomize the auxiliary matrix of observations according to the time axis
    # Randomized_X = X_tilde.transpose().sample(frac=1, axis=1, random_state=42) ## we transpose X as we want to have daily observations of the whole dataset !

    return (1/days)*np.dot(X_tilde.T, X_tilde) ## shape (695, 695)


def noised_array(eta, data, lookback_window, evaluation_window):

    # Extraction des rendements des actifs sur la période d'évaluation
    asset_returns = data.iloc[lookback_window[1]:lookback_window[1] + evaluation_window, :]

    if eta==1:

        return(asset_returns.mean())
    
    else:
        # Calcul des moyennes et des écarts-types des rendements pour chaque actif
        asset_means = asset_returns.mean()
        asset_std_devs = asset_returns.std()

        # Initialisation du DataFrame pour stocker les rendements bruités
        noised_returns = asset_means.copy()

        # Itération sur chaque colonne (actif) pour ajouter du bruit
        for asset in asset_means.index:
            # Calcul de l'écart-type du bruit pour cet actif
            noise_std_dev = np.sqrt(asset_std_devs[asset]*2 / eta - asset_std_devs[asset]*2)

            # Génération du bruit
            noise = np.random.normal(0, noise_std_dev)

            # Ajout du bruit aux rendements de l'actif
            noised_returns[asset] = asset_means[asset] + noise

        return noised_returns
    
    
def EWA_strat_returns(eta, beta, data, lookback_window, evaluation_window, short_selling=False, markowitz_type='min_volatility'):

    cov_matrix = EWA(beta, data, lookback_window)

    expected_returns = noised_array(eta, data, lookback_window, evaluation_window)

    if short_selling: 
        ef = EfficientFrontier(expected_returns=expected_returns, cov_matrix=cov_matrix, weight_bounds=(-1, 1)) 
        ## if we allow short-selling, then weights are not constrained to take nonnegative values, hence the (-1, 1) bounds
    else: 
        ef = EfficientFrontier(expected_returns=expected_returns, cov_matrix=cov_matrix, weight_bounds=(0, 1))

    if markowitz_type == 'min_volatility':
        ef.min_volatility()

    elif markowitz_type == 'max_sharpe':
        ef.max_sharpe(risk_free_rate=0)


    elif markowitz_type == 'expected_returns':
        ef.efficient_return(target_return=max(0, expected_returns.mean()))

    
    ## we get Markowitz weights 
    markowitz_weights = ef.clean_weights()
    
    ## we now compute the returns of the strategy
    EWA_portfolio_returns = pd.DataFrame(index=data.iloc[lookback_window[1]:lookback_window[1]+evaluation_window, :].index, columns=['return'], data=np.zeros(len(data.iloc[lookback_window[1]:lookback_window[1]+evaluation_window, :].index)))

    ##  each time we add : the current value of the return + the weighted "contribution" of the stock 'ticker' times 
    ##  is weight in the portfolio
    for ticker in data.columns: 
        EWA_portfolio_returns['return'] = EWA_portfolio_returns['return'] + data[ticker][lookback_window[1]:lookback_window[1]+evaluation_window]*markowitz_weights[ticker]

    return EWA_portfolio_returns


def EWA_sliding_window(number_of_window, eta, beta, data, lookback_window, evaluation_window, short_selling=False, markowitz_type='min_volatility'):

    PnL = []
    daily_PnL = []
    overall_return = pd.DataFrame()
    portfolio_value=[1] # we start with a value of 1, the list contain : the porfolio value at the start of each evaluation period
    lookback_window_0 = lookback_window

    for i in range(1, number_of_window + 1):

        try:

            EWA_returns_res = EWA_strat_returns(eta, beta, data, lookback_window_0, evaluation_window, short_selling, markowitz_type)

            overall_return = pd.concat([overall_return, EWA_returns_res])

            lookback_window_0 = [lookback_window[0] + evaluation_window*i, lookback_window[1] + evaluation_window*i]

            PnL = np.concatenate((PnL, np.reshape(np.cumprod(1 + EWA_returns_res)*portfolio_value[-1] - portfolio_value[-1], (evaluation_window,))))## car on réinvestit immédiatement après

            daily_PnL = np.concatenate((daily_PnL, np.reshape(np.cumprod(1 + EWA_returns_res)*portfolio_value[-1] - portfolio_value[-1], (evaluation_window,))))## car on réinvestit immédiatement après

            portfolio_value.append(portfolio_value[-1]+PnL[-1])

            print(f'step {i}/{number_of_window}, portfolio value: {portfolio_value[-1]:.4f}')

        except Exception as e:

            print(f"Error occurred at step {i}: {e}")

            return overall_return, PnL, portfolio_value, daily_PnL

    n = len(PnL)//evaluation_window

    for j in range(1, n):

        for i in range(1, evaluation_window+1):
            
            PnL[j*evaluation_window + i - 1] = PnL[j*evaluation_window + i - 1] + PnL[j*evaluation_window - 1]
    
    return overall_return, PnL, portfolio_value, daily_PnL





###########################################################################################################################
###########################################################################################################################
################################################# NAIVE PORTFOLIO #########################################################
###########################################################################################################################
###########################################################################################################################

def naive_returns(historical_data, lookback_window, evaluation_window):

    '''
    ----------------------------------------------------------------
    GENERAL IDEA : given the overall weights of each asset in the 
                portfolio, compute the portfolio return over an 
                evaluation window that does not overlap with the 
                lookback_window. 
    ----------------------------------------------------------------

    ----------------------------------------------------------------
    PARAMS : 

    - evaluation_window : integer, corresponding to the number of 
                        future days (in terms of historcal returns) 
                        on which we evaluate the portfolio

    - lookback_window : list of length 2, [start, end] corresponding 
                        to the range of the lookback_window

    - historical_data : cleaned pandas dataframe containing the returns 
                        of the stocks (!!! THE SHAPE OF THE DATA HAS TO BE
                        THE FOLLOWING: TICKERS NAME IN COLUMNS)

    - consolidated_W : numpy ndarray, containing the final weights 
                    of each asset, i.e. the overall portfolio 
                    weights

    - df : pandas dataframe containing the raw data
    ----------------------------------------------------------------

    ----------------------------------------------------------------
    OUTPUT : returns the portfolio return of each cluster in a 
            pandas dataframe
    ----------------------------------------------------------------
    '''

    portfolio_returns = pd.DataFrame(index=historical_data.iloc[lookback_window[1]:lookback_window[1]+evaluation_window, :].index, columns=['return'], data=np.zeros(len(historical_data.iloc[lookback_window[1]:lookback_window[1]+evaluation_window, :].index)))

    for ticker in historical_data.columns: 

    ##  each time we add :            the present value of the return + the weighted "contribution" of the stock 'ticker' times is weight in the portfolio
        portfolio_returns['return'] = portfolio_returns['return'] + historical_data[ticker][lookback_window[1]:lookback_window[1]+evaluation_window]*(1/len(historical_data.columns))

    return portfolio_returns


def naive_sliding_window(historical_data, lookback_window, evaluation_window, number_of_window):

    PnL = []
    daily_PnL = []
    overall_return = pd.DataFrame()
    portfolio_value=[1] #we start with a value of 1, the list contain : the porfolio value at the start of each evaluation period
    lookback_window_0 = lookback_window

    for i in range(1, number_of_window + 1):

        naive_returns_res = naive_returns(historical_data, lookback_window_0, evaluation_window)
        overall_return = pd.concat([overall_return, naive_returns_res])

        lookback_window_0 = [lookback_window[0] + evaluation_window*i, lookback_window[1] + evaluation_window*i]

        PnL = np.concatenate((PnL, np.reshape(np.cumprod(1 + naive_returns_res)*portfolio_value[-1] - portfolio_value[-1], (evaluation_window,))))## car on réinvestit immédiatement après
        daily_PnL = np.concatenate((daily_PnL, np.reshape(np.cumprod(1 + naive_returns_res)*portfolio_value[-1] - portfolio_value[-1], (evaluation_window,))))## car on réinvestit immédiatement après

        portfolio_value.append(portfolio_value[-1]+PnL[-1])

        print(f'step {i}/{number_of_window}, portfolio value: {portfolio_value[-1]:.4f}')

    n = len(PnL)//evaluation_window

    for j in range(1, n):

        for i in range(1, evaluation_window+1):
            
            PnL[j*evaluation_window + i - 1] = PnL[j*evaluation_window + i - 1] + PnL[j*evaluation_window - 1]
    
    return overall_return, PnL, portfolio_value, daily_PnL





######################### 2. We then split the (randomized) auxiliary observations into K non-overlapping folds of equal size #########################
def shuffle_split(data, K):
    # Initialize ShuffleSplit
    shuffle_split = ShuffleSplit(n_splits=K, test_size=0.2, random_state=42) 
    # test_size=0.2 : 20% des données pour l'ensemble de test, 80% pour l'ensemble d'entraînement.

    # Create empty list to store splits
    splits = []

    # Perform shuffling and splitting
    for train_index, test_index in shuffle_split.split(data.index):
        train_fold = [data.index[i] for i in train_index]
        test_fold = [data.index[i] for i in test_index]
        splits.append((train_fold, test_fold)) ## attention à cette structure

    return splits



######################### 3. For each K fold configuration, we estimate the sample eigenvectors from the training set #########################

def eigen_sample(data, beta, train_fold):
    ## 1. We extract the data corresponding to the returns of our assets (columns) during these d days (lines)
    X = data.loc[train_fold] ## shape days * number of stocks
    days = len(train_fold) 

    # Compute the weight matrix : shape (days, days) (if days = 250, shape (250, 250))
    W = np.sqrt(np.diag(days * (1 - beta) * beta**(np.arange(days)[::-1]) / (1 - beta**days)))  

    # We compute the auxiliary matrix
    X_tilde = np.dot(W, X)

    # We compute the training sample exponential moving average 
    sample_expo_cov = np.dot(X_tilde.T, X_tilde)

    # Calculer les vecteurs et valeurs propres de la matrice de covariance
    _, eigenvectors_train = np.linalg.eigh(sample_expo_cov) ## .eigh and not .eig so that the eigenvalues are real 

    return eigenvectors_train

def intra_fold_loss(data, test_fold, sample_eigenvector_i, beta): ## we test the data on this test fold

    ## 1. get the fold cardinality 
    fold_cardinality = len(test_fold) ## 20% of the observations

    ## 2. sample vector of the auxiliary observation matrix from the test fold (inspired from the code above)

    days = len(test_fold)
    X = data.loc[test_fold] ## shape (days, 695)

    ## 2. We slightly adjust the matrix of observations to get the auxiliary matrix that puts more weight on recent dates

    W = np.sqrt(np.diag(days * (1 - beta) * beta**(np.arange(days)[::-1]) / (1 - beta**days)))  # shape (days, days)
    X_tilde = pd.DataFrame(index=X.index, columns=X.columns, data=np.dot(W, X)) # shape (days, 695)

    res = (np.dot(sample_eigenvector_i, X_tilde.T) ** 2)  # shape (, 695) * (695, days) = (, days)
    result = np.sum(res) / fold_cardinality ## sum over days / size of the test sample

    return result

def average_loss(data, splits, index, beta):

    res = 0 ## to stock the overall loss

    for (train_fold, test_fold) in splits:

        ## sur chaque fold, on calcule les sample eigenvectors à partir du training fold correspondant

        sample_eigenvector_i = eigen_sample(data=data, beta=beta, train_fold=train_fold)[:, index] ## on ne garde que l'eigenvector correspondant au bon index

        ## sur chaque fold, on calcule la perte au sein du fold à partir de l'échantillon de test

        res = res + intra_fold_loss(data=data, test_fold=test_fold, sample_eigenvector_i=sample_eigenvector_i, beta=beta)

    res = res / len(splits) ## we average by the number of folds (which corresponds to the lengths of the splits)

    return res

def eigenvalue_estimator(data, splits, beta):

    number_of_stocks = len(data.columns) ## COLUMNS HAVE TO BE COMPOSED OF THE STOCKS TICKERS

    xi = np.zeros(number_of_stocks)  # initialisation de x

    for i in tqdm(range(number_of_stocks), desc='Calcul en cours', unit='itération'):
        xi[i] = average_loss(data=data, splits=splits, index=i, beta=beta)   
                       
    return xi

def EMA_CV(data, beta, lookback_window, number_of_folds):

    days = len(lookback_window)
    ## compute the sample exponential moving average correlation matrix
    W = np.sqrt(np.diag(days * (1 - beta) * beta**(np.arange(lookback_window[0], lookback_window[1])[::-1]) / (1 - beta**days)))  
    X_tilde = np.dot(W, data)  # Produit matriciel de X' et W
    S = np.dot(X_tilde.T, X_tilde)

    ## compute the eigenvectors of S
    _, eigenvectors = np.linalg.eigh(S)

    ## computes the estimator 
    X_tilde = auxilary_matrix(lookback_window=lookback_window, beta=beta, df_cleaned=data)
    splits = shuffle_split(data=X_tilde, K=number_of_folds)
    eigenvalue_est = eigenvalue_estimator(data=data, splits=splits, beta=beta)

    # Initialisation de Sigma avec des zéros
    Sigma = np.zeros((S.shape[0], S.shape[1]), dtype=np.complex128)

    # Parcourir chaque vecteur propre et valeur propre
    for i in range(len(data.columns)):
        xi_dagger = eigenvalue_est[i]  # Conjugue de xi
        ui = eigenvectors[:, i]  # i-ème vecteur propre

        # Calcul du produit externe xi^† * ui * ui^† et addition à Sigma
        Sigma += xi_dagger * np.outer(ui, ui) 

    # Sigma est maintenant la somme des produits xi^† * ui * ui^†
    Sigma = pd.DataFrame(index=data.columns, columns=data.columns, data=np.real(Sigma))

    return Sigma
