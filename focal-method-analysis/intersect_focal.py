import sys, json, argparse
from collections import Counter


def norm(name):
    # llm may return Class.method or method(...); compare on the bare method name
    if not name:
        return None
    n = str(name).split("(")[0].strip()   # drop any (args)
    n = n.split(".")[-1]                    # drop Class. qualifier
    return n


def load(path, name_key):
    try:
        data = json.load(open(path, encoding="utf-8"))
    except OSError as e:
        print(f"[error] cannot read {path}: {e}", file=sys.stderr); sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[error] {path} is not valid json: {e}", file=sys.stderr); sys.exit(1)
    if not isinstance(data, list):
        print(f"[error] {path} should be a list of test entries", file=sys.stderr); sys.exit(1)
    out = {}
    for e in data:
        if not isinstance(e, dict) or name_key not in e:
            continue
        t = e[name_key]
        if t in out:
            print(f"[warn] duplicate test name in {path}: {t} (keeping first)", file=sys.stderr)
            continue
        out[t] = e
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jaccard_json")
    ap.add_argument("llm_json")
    ap.add_argument("out_json")
    a = ap.parse_args()

    jac = load(a.jaccard_json, "test_name")
    llm = load(a.llm_json, "test_name")

    results = []
    for t in sorted(set(jac) | set(llm)):
        j = jac.get(t, {})
        l = llm.get(t, {})
        jm = j.get("focal_method")
        lm = l.get("llm_focal_method")
        jn, ln = norm(jm), norm(lm)

        if t not in jac:
            status = "missing from jaccard run"
        elif t not in llm:
            status = "missing from llm run"
        elif jn and ln and jn == ln:
            status = "agreed"
        elif jm and lm:
            status = "disagreed"
        elif not jm and not lm:
            status = "neither found a method"
        elif jm:
            status = "jaccard only"
        else:
            status = "llm only"

        # eq 2: focal method is valid only when both techniques name the same one
        agreed = status == "agreed"
        results.append({
            "test_name": t,
            "focal_method": jm if agreed else None,
            "status": status,
            "jaccard_focal": jm,
            "jaccard_score": j.get("score"),
            "llm_focal": lm,
            "llm_probability": l.get("llm_probability"),
            "llm_error": l.get("error"),
        })

    json.dump(results, open(a.out_json, "w"), indent=2)

    counts = Counter(r["status"] for r in results)
    total = len(results)
    agreed = counts.get("agreed", 0)
    print(f"{total} test(s) compared, written to {a.out_json}\n")
    for r in results:
        mark = "OK " if r["status"] == "agreed" else "   "
        print(f"  {mark}{r['test_name'][:45]:45} jaccard={str(r['jaccard_focal']):24} "
              f"llm={str(r['llm_focal']):24} {r['status']}")
    print(f"\nconfirmed focal methods (both agree): {agreed}/{total}")
    for k, v in counts.most_common():
        if k != "agreed":
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
