"""Multi-hot encoding"""
import numpy as np
import pandas as pd
import copy
from sklearn.base import BaseEstimator, TransformerMixin
from category_encoders.ordinal import OrdinalEncoder
import category_encoders.utils as util

__author__ = 'fullflu'


class MultiHotEncoder(BaseEstimator, TransformerMixin):
    """Multihot coding for categorical features, produces one feature per category, each non-negative.

    Parameters
    ----------

    verbose: int
        integer indicating verbosity of output. 0 for none.
    cols: list
        a list of columns to encode, if None, all string columns will be encoded.
    drop_invariant: bool
        boolean for whether or not to drop columns with 0 variance.
    return_df: bool
        boolean for whether to return a pandas DataFrame from transform (otherwise it will be a numpy array).
    impute_missing: bool
        boolean for whether or not to apply the logic for handle_unknown, will be deprecated in the future.
    handle_unknown: str
        options are 'error', 'ignore' and 'impute', defaults to 'impute', which will impute the category -1. Warning: if
        impute is used, an extra column will be added in if the transform matrix has unknown categories. This can cause
        unexpected changes in the dimension in some cases.
    use_cat_names: bool
        if True, category values will be included in the encoded column names. Since this can result into duplicate column names, duplicates are suffixed with '#' symbol until a unique name is generated.
        If False, category indices will be used instead of the category values.
    multiple_split_string: str
        Represents which string we should split input

    Example
    -------
    >>> from category_encoders import *
    >>> import pandas as pd
    >>> from sklearn.datasets import load_boston
    >>> bunch = load_boston()
    >>> X = pd.DataFrame(bunch.data, columns=bunch.feature_names)
    >>> enc = MultiHotEncoder(cols=['RAD_mask'])
    >>> X_mask = enc.create_boston_RAD(X)
    >>> numeric_dataset = enc.transform(X_mask, normilize=False)

    or
    >>> from category_encoders import *
    >>> numetic_dataset = MultiHotEncoder().run_example(normalize=False)
    >>> numetic_normalized_dataset = MultiHotEncoder().run_example(normalize=True)

    >>> print(numeric_dataset.info())
    <class 'pandas.core.frame.DataFrame'>
    RangeIndex: 506 entries, 0 to 505
    Data columns (total 23 columns):
    CRIM                506 non-null float64
    ZN                  506 non-null float64
    INDUS               506 non-null float64
    CHAS                506 non-null float64
    NOX                 506 non-null float64
    RM                  506 non-null float64
    AGE                 506 non-null float64
    DIS                 506 non-null float64
    RAD                 506 non-null float64
    TAX                 506 non-null float64
    PTRATIO             506 non-null float64
    B                   506 non-null float64
    LSTAT               506 non-null float64
    RAD_mask_4          506 non-null int64
    RAD_mask_6          506 non-null int64
    RAD_mask_5          506 non-null int64
    RAD_mask_2          506 non-null int64
    RAD_mask_8          506 non-null int64
    RAD_mask_9          506 non-null int64
    RAD_mask_3          506 non-null int64
    RAD_mask_7          506 non-null int64
    RAD_mask_1          506 non-null int64
    RAD_mask_withnan    449 non-null object
    dtypes: float64(13), int64(9), object(1)
    memory usage: 91.0+ KB
    None

    References
    ----------

    .. [1] Contrast Coding Systems for categorical variables.  UCLA: Statistical Consulting Group. from
    https://stats.idre.ucla.edu/r/library/r-library-contrast-coding-systems-for-categorical-variables/.

    .. [2] Gregory Carey (2003). Coding Categorical Variables, from
    http://psych.colorado.edu/~carey/Courses/PSYC5741/handouts/Coding%20Categorical%20Variables%202006-03-03.pdf


    """

    def __init__(self, verbose=0, cols=None, drop_invariant=False, return_df=True, impute_missing=True, handle_unknown='impute', use_cat_names=False, multiple_split_string="|"):
        self.return_df = return_df
        self.drop_invariant = drop_invariant
        self.drop_cols = []
        self.mapping = None
        self.verbose = verbose
        self.cols = cols
        self.ordinal_encoder = None
        self._dim = None
        self.impute_missing = impute_missing
        self.handle_unknown = handle_unknown
        self.use_cat_names = use_cat_names
        self.feature_names = None
        self.multiple_split_string = multiple_split_string

    def fit(self, X, y=None, **kwargs):
        """Fit encoder according to X and y.

        Parameters
        ----------

        X : array-like, shape = [n_samples, n_features]
            Training vectors, where n_samples is the number of samples
            and n_features is the number of features.
        y : array-like, shape = [n_samples]
            Target values.

        Returns
        -------

        self : encoder
            Returns self.

        """

        # first check the type
        X = util.convert_input(X).fillna(np.nan)

        self._dim = X.shape[1]

        # if columns aren't passed, just use every string column
        if self.cols is None:
            self.cols = util.get_obj_cols(X)
        else:
            self.cols = util.convert_cols_to_list(self.cols)

        # Indicate no transformation has been applied yet
        self.mapping, self.col_index_mapping = self.generate_mapping(X, cols=self.cols, multiple_split_string=self.multiple_split_string)

        return self

        X_temp = self.transform(X, override_return_df=True)
        self.feature_names = list(X_temp.columns)

        if self.drop_invariant:
            self.drop_cols = []
            generated_cols = util.get_generated_cols(X, X_temp, self.cols)
            self.drop_cols = [x for x in generated_cols if X_temp[x].var() <= 10e-5]
            try:
                [self.feature_names.remove(x) for x in self.drop_cols]
            except KeyError as e:
                if self.verbose > 0:
                    print("Could not remove column from feature names."
                    "Not found in generated cols.\n{}".format(e))

        return self

    @staticmethod
    def generate_mapping(X_in, mapping=None, cols=None, impute_missing=True, handle_unknown='impute', multiple_split_string="|"):
        """
        Parameters
        ----------

        X_in : array-like, shape = [n_samples, n_features]
        mapping: list-like
        cols: list
            Represents categorical feature names
        multiple_string_split: str
            Represents which string we should split input
        Returns
        -------

        mapping_out : list-like
            mapping used for multi-hot encoding
        col_index_mapping: dict
            dictionary which transforms col name into index of mapping_out
        """
        X = X_in.copy(deep=True)
        # dictionary which maps col name to index of ordinal mapping
        col_index_mapping = {}

        if cols is None:
            cols = X.columns.values

        mapping_out = []
        for i, col in enumerate(cols):
            # append index mapping
            col_index_mapping[col] = i
            candidate_of_col = set()
            tmp = (X[col].map(lambda x: candidate_of_col.update(x.split(multiple_split_string))
                if type(x) == str
                else candidate_of_col.add(str(int(x)))
                if (type(x) == float or type(x) == int) and x == x
                else candidate_of_col.add(x)))

            col_mappings = []
            # val to new_colname mapping
            val_newcolname_mappings = {}
            for i, class_ in enumerate(candidate_of_col):
                n_col_name = str(col) + '_%s' % (i + 1,)
                col_mappings.append({'new_col_name': n_col_name, 'val': class_})
                val_newcolname_mappings[class_] = n_col_name

            mapping_out.append({'col': col, 'mapping': col_mappings, 'data_type': X[col].dtype, 'candidate_set': candidate_of_col, "val_newcolname_mapping": val_newcolname_mappings})

        return mapping_out, col_index_mapping

    def transform(self, X, override_return_df=False, normalize=True):
        """Perform the transformation to new categorical data.

        Parameters
        ----------

        X : array-like, shape = [n_samples, n_features]
        normalize: bool
            If true, the summation of transformed output is 1 for each categorical column

        Returns
        -------

        p : array, shape = [n_samples, n_numeric + N]
            Transformed values with encoding applied.

        """

        if self._dim is None:
            raise ValueError(
                'Must train encoder before it can be used to transform data.')

        # first check the type
        X = util.convert_input(X).fillna(np.nan)

        # then make sure that it is the right size
        if X.shape[1] != self._dim:
            raise ValueError('Unexpected input dimension %d, expected %d' % (
                X.shape[1], self._dim, ))

        if not self.cols:
            return X if self.return_df else X.values

        X = self.get_dummies(X, mapping=self.mapping, multiple_split_string=self.multiple_split_string, normalize=normalize)

        if self.drop_invariant:
            for col in self.drop_cols:
                X.drop(col, 1, inplace=True)

        if self.return_df or override_return_df:
            return X
        else:
            return X.values

    def get_dummies(self, X_in, mapping, multiple_split_string="|", normalize=True):
        """
        Convert numerical variable into dummy variables
        Parameters
        ----------
        X_in: DataFrame
        mapping: list-like
              Contains mappings of column to be transformed to it's new columns and value represented
        multiple_split_string: str
              Represents which string we should split input
        normalize: bool
            If true, the summation of transformed output is 1 for each categorical column

        Returns
        -------
        dummies : DataFrame
        """

        X = X_in.copy(deep=True)

        cols = X.columns.values.tolist()

        for switch in mapping:
            col = switch.get('col')
            mod = switch.get('mapping')
            inv_map = switch.get('val_newcolname_mapping')
            new_columns = []
            # for column_mapping in mod:
            #     new_col_name = column_mapping['new_col_name']
            #     X[new_col_name] = 0
            for column_mapping in mod:
                new_col_name = column_mapping['new_col_name']
                val = column_mapping['val']
                # multi-hot encoder
                X[new_col_name] = (X[col].map(lambda x: 1
                    if (type(x) == str and val in x.split(self.multiple_split_string))
                    or (val != val and x != x)
                    or ((type(x) == int or type(x) == float) and x == x and val == str(int(x)))
                    else 0))
                new_columns.append(new_col_name)
            if normalize:
                zero_index = X[new_columns].sum(axis=1) == 0
                X.loc[~zero_index, new_columns] = X.loc[~zero_index, new_columns].div(X.loc[~zero_index, new_columns].sum(axis=1), axis=0)
            old_column_index = cols.index(col)
            cols[old_column_index: old_column_index + 1] = list(set(new_columns))

        return X.reindex(columns=cols)

    @staticmethod
    def create_boston_RAD(df, col="RAD"):
        """
        Create ambiguous feature of the RAD column in boston dataset, used to check Example.
        
        Returns
        -------
        df: DataFrame
        """
        mapping = {1: "1|2|3", 2: "1|2|3", 3: "1|2|3", 4: 4, 5: 5, 6: 6, 7: "7|8", 8: "7|8", 24: 24}
        df = df.copy()
        shuffle_idx = np.arange(df.shape[0]) % 2 == 0
        df[col + "_mask"] = df[col]
        df.loc[shuffle_idx, col + "_mask"] = df.loc[shuffle_idx, col + "_mask"].map(mapping)
        nan_idx = np.arange(df.shape[0]) % 9 == 0
        df[col + "_mask_withnan"] = df[col + "_mask"]
        df.loc[nan_idx, col + "_mask_withnan"] = np.nan
        return df

    @staticmethod
    def run_example(normalize=True):
        """
        Run Example
        
        Returns
        -------
        df: DataFrame
        """
        from category_encoders import MultiHotEncoder
        from sklearn.datasets import load_boston
        bunch = load_boston()
        X = pd.DataFrame(bunch.data, columns=bunch.feature_names)
        enc = MultiHotEncoder(cols=['RAD_mask'])
        X_mask = enc.create_boston_RAD(X)
        enc.fit(X_mask)
        numeric_dataset = enc.transform(X_mask, normalize=normalize)
        return numeric_dataset