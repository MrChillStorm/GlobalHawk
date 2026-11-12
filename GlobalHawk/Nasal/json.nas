# JSON for the command link: FlightGear's Nasal has none. decode() gives hashes, vectors, numbers and strings
# (true is 1, false 0, null nil); encode() writes them back. A Nasal scalar that holds text is written as a string
# and one that holds a number as a number, whatever the text looks like.

var JSON = {
    T: { json: "true" },                  # write these where the station expects true and false
    F: { json: "false" },

    is_string: func(x) {
        if (typeof(x) != "scalar") return 0;
        var err = [];
        call(size, [x], nil, nil, err);      # size() takes text, not a number
        return size(err) == 0;
    },
    is_number: func(x) {
        return typeof(x) == "scalar" and !JSON.is_string(x) and x == x and x - x == 0;
    },

    quote: func(s) {
        var out = "\"";
        for (var i = 0; i < size(s); i += 1) {
            var c = s[i];
            if (c == 34) out ~= "\\\"";
            elsif (c == 92) out ~= "\\\\";
            elsif (c == 10) out ~= "\\n";
            elsif (c == 13) out ~= "\\r";
            elsif (c == 9) out ~= "\\t";
            elsif (c < 32) out ~= " ";
            else out ~= chr(c);
        }
        return out ~ "\"";
    },

    number: func(x) {
        if (x != x or x - x != 0) return "null";                       # not a number, or infinite
        if (x == int(x) and x < 1e15 and x > -1e15) return sprintf("%d", x);
        return sprintf("%.15g", x);
    },

    encode: func(v) {
        var t = typeof(v);
        if (t == "nil") return "null";
        if (t == "scalar") return JSON.is_string(v) ? JSON.quote(v) : JSON.number(v);
        if (t == "vector") {
            var out = "[";
            forindex (var i; v) out ~= (i ? "," : "") ~ JSON.encode(v[i]);
            return out ~ "]";
        }
        if (t == "hash") {
            if (id(v) == id(JSON.T) or id(v) == id(JSON.F)) return v.json;
            var out = "{";
            var n = 0;
            foreach (var k; sort(keys(v), func(a, b) cmp(a, b))) {
                if (typeof(v[k]) == "func") continue;
                out ~= (n ? "," : "") ~ JSON.quote(k ~ "") ~ ":" ~ JSON.encode(v[k]);
                n += 1;
            }
            return out ~ "}";
        }
        return "null";
    },

    # ---- reading
    decode: func(text) {
        var p = { s: text, i: 0, n: size(text) };
        var v = JSON._value(p);
        JSON._space(p);
        if (p.i != p.n) die("JSON: text after the value");
        return v;
    },
    # nil and an error text if it cannot be read, as [value, error]
    try: func(text) {
        if (!JSON.is_string(text)) return [nil, "not text"];
        var err = [];
        var v = call(JSON.decode, [text], JSON, nil, err);
        return size(err) ? [nil, err[0]] : [v, nil];
    },
    _space: func(p) {
        while (p.i < p.n and (p.s[p.i] == 32 or p.s[p.i] == 9 or p.s[p.i] == 10 or p.s[p.i] == 13)) p.i += 1;
    },
    _word: func(p, w) {
        if (substr(p.s, p.i, size(w)) != w) die("JSON: bad word");
        p.i += size(w);
    },
    _value: func(p) {
        JSON._space(p);
        if (p.i >= p.n) die("JSON: ends early");
        var c = p.s[p.i];
        if (c == 123) {                                   # {
            p.i += 1;
            var h = {};
            JSON._space(p);
            if (p.i < p.n and p.s[p.i] == 125) { p.i += 1; return h; }
            while (1) {
                JSON._space(p);
                if (p.i >= p.n or p.s[p.i] != 34) die("JSON: a name was expected");
                var k = JSON._string(p);
                JSON._space(p);
                if (p.i >= p.n or p.s[p.i] != 58) die("JSON: a colon was expected");
                p.i += 1;
                h[k] = JSON._value(p);
                JSON._space(p);
                if (p.i >= p.n) die("JSON: ends early");
                if (p.s[p.i] == 44) { p.i += 1; continue; }
                if (p.s[p.i] == 125) { p.i += 1; return h; }
                die("JSON: a comma or a brace was expected");
            }
        }
        if (c == 91) {                                    # [
            p.i += 1;
            var v = [];
            JSON._space(p);
            if (p.i < p.n and p.s[p.i] == 93) { p.i += 1; return v; }
            while (1) {
                append(v, JSON._value(p));
                JSON._space(p);
                if (p.i >= p.n) die("JSON: ends early");
                if (p.s[p.i] == 44) { p.i += 1; continue; }
                if (p.s[p.i] == 93) { p.i += 1; return v; }
                die("JSON: a comma or a bracket was expected");
            }
        }
        if (c == 34) return JSON._string(p);
        if (c == 116) { JSON._word(p, "true"); return 1; }
        if (c == 102) { JSON._word(p, "false"); return 0; }
        if (c == 110) { JSON._word(p, "null"); return nil; }
        var j = p.i;
        while (j < p.n and (p.s[j] == 43 or p.s[j] == 45 or p.s[j] == 46 or p.s[j] == 69 or p.s[j] == 101 or (p.s[j] >= 48 and p.s[j] <= 57))) j += 1;
        var x = num(substr(p.s, p.i, j - p.i));
        if (j == p.i or x == nil) die("JSON: a value was expected");
        p.i = j;
        return x + 0;
    },
    _string: func(p) {
        p.i += 1;
        var out = "";
        var from = p.i;
        while (1) {
            if (p.i >= p.n) die("JSON: a string does not end");
            var c = p.s[p.i];
            if (c == 34) {
                out ~= substr(p.s, from, p.i - from);
                p.i += 1;
                return out;
            }
            if (c == 92) {
                out ~= substr(p.s, from, p.i - from);
                if (p.i + 1 >= p.n) die("JSON: a string does not end");
                var e = p.s[p.i + 1];
                if (e == 110) out ~= "\n";
                elsif (e == 116) out ~= "\t";
                elsif (e == 114) out ~= "\r";
                elsif (e == 98 or e == 102) out ~= " ";
                elsif (e == 117) { out ~= "?"; p.i += 4; }             # \uXXXX: not kept
                else out ~= chr(e);
                p.i += 2;
                from = p.i;
                continue;
            }
            p.i += 1;
        }
    },
};
