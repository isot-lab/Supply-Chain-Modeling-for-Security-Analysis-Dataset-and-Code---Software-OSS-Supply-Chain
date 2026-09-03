"""Shared helpers for the experiment notebooks (01-08)."""

import time

import numpy as np
import pandas as pd
import networkx as nx
import scipy.sparse as sp
from scipy.sparse import csgraph
from scipy.sparse.csgraph import dijkstra
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

SEED = 42
N_JOBS = 4                 # bounded: an unbounded loky pool per fit leaks workers
N_LANDMARKS = 128          # landmark count for approximate harmonic closeness
MIN_VIEW_POS = 10          # a label view below this many positives is unusable
MIN_PER_CLASS = 5          # per-level AUROC needs this many of each class

ECO_TITLES = {"npm": "npm", "pypi": "PyPI", "maven": "Maven"}


def read_csv_literal(path, **kw):
    # `nan` / `null` are real package names -- only an empty field is missing.
    return pd.read_csv(path, keep_default_na=False, na_values=[""], low_memory=False, **kw)


def make_views(label_arr, min_pos=MIN_VIEW_POS, restrict_to=None):
    """The two label views: `compromised` drops vulnerable rows, `risky` merges them."""
    n = len(label_arr)
    m_vuln, m_comp = (label_arr == -1), (label_arr == 1)
    views = {
        "compromised": {"keep": ~m_vuln, "y": m_comp[~m_vuln].astype(np.int64)},
        "risky":       {"keep": np.ones(n, bool), "y": (m_comp | m_vuln).astype(np.int64)},
    }
    return {k: v for k, v in views.items()
            if int(v["y"].sum()) >= min_pos and (restrict_to is None or k in restrict_to)}


def build_graph_structures(src_arr, tgt_arr, n_nodes):
    A = sp.csr_matrix((np.ones(len(src_arr), np.int8), (src_arr, tgt_arr)), shape=(n_nodes, n_nodes))
    n_scc, scc = csgraph.connected_components(A, directed=True, connection="strong")
    cs, ct = scc[src_arr], scc[tgt_arr]; keep = cs != ct
    dag_edges = (np.unique(np.stack([cs[keep], ct[keep]], axis=1), axis=0) if keep.any()
                 else np.empty((0, 2), np.int64))
    ones = np.ones(len(dag_edges), np.int8)
    dep_csr = sp.csr_matrix((ones, (dag_edges[:, 0], dag_edges[:, 1])), shape=(n_scc, n_scc))
    inf_csr = sp.csr_matrix((ones, (dag_edges[:, 1], dag_edges[:, 0])), shape=(n_scc, n_scc))
    indeg = np.diff(dep_csr.indptr).astype(np.int64).copy()
    inf_ip, inf_ix = inf_csr.indptr, inf_csr.indices
    queue = [int(u) for u in np.flatnonzero(indeg == 0)]; topo, head = [], 0
    while head < len(queue):
        u = queue[head]; head += 1; topo.append(u)
        for v in inf_ix[inf_ip[u]:inf_ip[u + 1]]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(int(v))
    assert len(topo) == n_scc, "condensation is not a DAG"
    lev = np.zeros(n_scc, np.int32)
    for u in topo:
        vs = inf_ix[inf_ip[u]:inf_ip[u + 1]]
        if len(vs):
            lev[vs] = np.maximum(lev[vs], lev[u] + 1)
    return {"n_scc": n_scc, "scc": scc, "dag_edges": dag_edges, "dep_csr": dep_csr,
            "inf_csr": inf_csr, "topo": np.array(topo), "lev": lev}


def reach_weighted_sums(succ_indptr, succ_indices, order, weights,
                        slab_bits=8192, row_chunk=4096, label=""):
    n, k = weights.shape; w32 = np.ascontiguousarray(weights, np.float32)
    sums = np.zeros((n, k)); t0 = time.time()
    order_nz = [int(u) for u in order if succ_indptr[u + 1] > succ_indptr[u]]
    for c0 in range(0, n, slab_bits):
        c1 = min(c0 + slab_bits, n); nbits = c1 - c0
        reach = np.zeros((n, (nbits + 7) // 8), np.uint8)
        js = np.arange(c0, c1); reach[js, (js - c0) >> 3] = (128 >> ((js - c0) & 7)).astype(np.uint8)
        for u in order_nz:
            a, b = succ_indptr[u], succ_indptr[u + 1]
            reach[u] |= np.bitwise_or.reduce(reach[succ_indices[a:b]], axis=0)
        for r0 in range(0, n, row_chunk):
            r1 = min(r0 + row_chunk, n)
            sums[r0:r1] += np.unpackbits(reach[r0:r1], axis=1, count=nbits).astype(np.float32) @ w32[c0:c1]
    print(f"  reachability [{label}] {time.time()-t0:.1f}s")
    return sums


def compute_graph_features(src, tgt, n_nodes, seed=SEED, n_landmarks=N_LANDMARKS, verbose=True):
    # Returns (DataFrame of the canonical 11, extras dict). Used on the full corpus in
    # notebook 01; notebook 07 rebuilds per-rung features with its own array variant.
    gs = build_graph_structures(src, tgt, n_nodes)
    n_scc, scc, lev, topo = gs["n_scc"], gs["scc"], gs["lev"], gs["topo"]
    scc_size = np.bincount(scc, minlength=n_scc).astype(np.float64)
    conn = np.zeros(n_nodes, bool); conn[src] = True; conn[tgt] = True
    in_degree = np.bincount(tgt, minlength=n_nodes).astype(np.int64)
    out_degree = np.bincount(src, minlength=n_nodes).astype(np.int64)

    drive = reach_weighted_sums(gs["inf_csr"].indptr, gs["inf_csr"].indices, topo[::-1],
                                scc_size[:, None], label="driving" if verbose else "")
    depnd = reach_weighted_sums(gs["dep_csr"].indptr, gs["dep_csr"].indices, topo,
                                scc_size[:, None], label="dependence" if verbose else "")
    driving_power = (drive[:, 0] - 1.0)[scc]
    dependence_power = (depnd[:, 0] - 1.0)[scc]

    # PageRank on the dependency orientation, over the connected subgraph
    conn_idx = np.flatnonzero(conn); nc = conn_idx.size
    pagerank = np.zeros(n_nodes)
    if nc:
        remap = np.full(n_nodes, -1, np.int64); remap[conn_idx] = np.arange(nc)
        A_pd = sp.csr_matrix((np.ones(len(src)), (remap[src], remap[tgt])), shape=(nc, nc))
        AT = A_pd.T.tocsr(); outd = np.asarray(A_pd.sum(1)).ravel(); pr = np.full(nc, 1.0 / nc)
        for _ in range(200):
            w = np.where(outd > 0, pr / np.where(outd > 0, outd, 1.0), 0.0)
            pr2 = 0.15 / nc + 0.85 * (AT @ w + pr[outd == 0].sum() / nc)
            if np.abs(pr2 - pr).sum() < 1e-12:
                pr = pr2; break
            pr = pr2
        pagerank[conn_idx] = pr

    # HITS on the package-level adjacency
    A_pkg = sp.csr_matrix((np.ones(len(src)), (src, tgt)), shape=(n_nodes, n_nodes))
    h = np.ones(n_nodes) / max(n_nodes, 1); a = np.zeros(n_nodes)
    for _ in range(80):
        a = A_pkg.T @ h; a /= max(np.linalg.norm(a), 1e-300)
        h2 = A_pkg @ a; h2 /= max(np.linalg.norm(h2), 1e-300)
        if np.abs(h2 - h).sum() < 1e-12:
            h = h2; break
        h = h2

    # clustering + landmark harmonic closeness on the undirected graph
    G_und = nx.Graph(); G_und.add_nodes_from(range(n_nodes))
    G_und.add_edges_from(zip(src.tolist(), tgt.tolist()))
    clustering = np.zeros(n_nodes)
    for k, v in nx.clustering(G_und).items():
        clustering[k] = v
    closeness = np.zeros(n_nodes)
    if nc:
        lm_rng = np.random.default_rng(seed)
        L = min(n_landmarks, nc)
        landmarks = conn_idx[lm_rng.choice(nc, size=L, replace=False)]
        A_und = (A_pkg + A_pkg.T); A_und.data[:] = 1
        dists = dijkstra(A_und, directed=False, indices=landmarks, unweighted=True)
        with np.errstate(divide="ignore"):
            inv = np.where(dists > 0, 1.0 / dists, 0.0)
        closeness = np.nanmean(np.where(np.isfinite(inv), inv, 0.0), axis=0)

    feats = pd.DataFrame({
        "warfield_level": lev[scc].astype(np.float64),
        "in_degree": in_degree.astype(np.float64),
        "out_degree": out_degree.astype(np.float64),
        "log1p_driving_power": np.log1p(np.maximum(driving_power, 0)),
        "log1p_dependence_power": np.log1p(np.maximum(dependence_power, 0)),
        "scc_size": scc_size[scc],
        "pagerank": pagerank,
        "hits_hub": h,
        "hits_auth": a,
        "clustering": clustering,
        "closeness": closeness,
    })[GRAPH_FEATURES]
    extras = {"gs": gs, "scc": scc, "conn": conn, "driving_power": driving_power,
              "dependence_power": dependence_power, "n_scc": n_scc}
    return feats, extras


GRAPH_FEATURES = [
    "warfield_level",          # longest dependency chain below the package
    "in_degree",               # direct dependents, in-dataset
    "out_degree",              # direct dependencies, in-dataset
    "log1p_driving_power",     # log1p transitive dependents  (forward closure)
    "log1p_dependence_power",  # log1p transitive dependencies (backward closure)
    "scc_size",                # size of the package's strongly connected component
    "pagerank",                # PageRank on the dependency orientation
    "hits_hub",                # HITS hub score
    "hits_auth",               # HITS authority score
    "clustering",              # local clustering coefficient (undirected)
    "closeness",               # landmark-approximated harmonic closeness (undirected)
]


# The five MeMPtec baseline families (notebooks 02 and 03). NOT the factory used by
# notebook 04, whose base-score models differ deliberately (GBM/DRF class_weight, DRF 300).
def make_models():
    # SimpleImputer(median) is fit on the training fold only (Pipeline guarantees this),
    # so no test-fold information reaches the imputation.
    svm_base = LinearSVC(max_iter=3000, C=1.0, class_weight="balanced", random_state=SEED)
    return {
        "SVM": Pipeline([("impute", SimpleImputer(strategy="median")),
                         ("scaler", StandardScaler()),
                         ("clf", CalibratedClassifierCV(svm_base, cv=3))]),
        "GLM": Pipeline([("impute", SimpleImputer(strategy="median")),
                         ("scaler", StandardScaler()),
                         ("clf", LogisticRegression(max_iter=2000, C=1.0,
                                                    class_weight="balanced",
                                                    solver="lbfgs", random_state=SEED))]),
        # native NaN support (verified against scikit-learn 1.9)
        "GBM": HistGradientBoostingClassifier(max_iter=200, max_depth=5, random_state=SEED),
        "DRF": RandomForestClassifier(n_estimators=200, n_jobs=N_JOBS, random_state=SEED),
        "DL":  Pipeline([("impute", SimpleImputer(strategy="median")),
                         ("scaler", StandardScaler()),
                         ("clf", MLPClassifier(hidden_layer_sizes=(128, 64, 32),
                                               activation="relu", solver="adam",
                                               max_iter=300, early_stopping=True,
                                               validation_fraction=0.1, random_state=SEED))]),
    }


BUCKET_ORDER = ["isolated", "0", "1", "2", "3", "4", "5-9", "10-19", "20+"]


def to_bucket(lv, iso):
    if iso:      return "isolated"
    if lv <= 4:  return str(int(lv))
    if lv <= 9:  return "5-9"
    if lv <= 19: return "10-19"
    return "20+"
