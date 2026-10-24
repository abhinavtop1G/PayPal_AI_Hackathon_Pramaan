package com.pramaan.sdk.core

/**
 * A small JSON writer and parser, so the SDK has no dependencies and its core runs (and is tested) on a plain JVM.
 * Objects become `Map<String, Any?>`, arrays `List<Any?>`, numbers `Double`.
 */
object Json {
    fun write(v: Any?): String = StringBuilder().also { write(v, it) }.toString()

    @Suppress("UNCHECKED_CAST")
    private fun write(v: Any?, sb: StringBuilder) {
        when (v) {
            null -> sb.append("null")
            is String -> string(v, sb)
            is Boolean -> sb.append(v)
            is Double -> if (v.isFinite()) sb.append(num(v)) else sb.append("null")
            is Float -> write(v.toDouble(), sb)
            is Number -> sb.append(v.toLong())
            is Map<*, *> -> {
                sb.append('{')
                var first = true
                for ((k, x) in v as Map<String, Any?>) {
                    if (!first) sb.append(',')
                    first = false
                    string(k, sb)
                    sb.append(':')
                    write(x, sb)
                }
                sb.append('}')
            }
            is Iterable<*> -> {
                sb.append('[')
                v.forEachIndexed { i, x ->
                    if (i > 0) sb.append(',')
                    write(x, sb)
                }
                sb.append(']')
            }
            is DoubleArray -> write(v.toList(), sb)
            is JsonValue -> write(v.toJson(), sb)
            else -> string(v.toString(), sb)
        }
    }

    private fun num(d: Double): String =
        if (d == Math.rint(d) && kotlin.math.abs(d) < 1e15) d.toLong().toString() else d.toString()

    private fun string(s: String, sb: StringBuilder) {
        sb.append('"')
        for (c in s) {
            when (c) {
                '"' -> sb.append("\\\"")
                '\\' -> sb.append("\\\\")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                '\b' -> sb.append("\\b")
                '\u000C' -> sb.append("\\f")
                else -> if (c < ' ') sb.append(String.format("\\u%04x", c.code)) else sb.append(c)
            }
        }
        sb.append('"')
    }

    fun parse(s: String): Any? = Parser(s).run {
        val v = value()
        ws()
        if (i != s.length) error("trailing characters")
        v
    }

    private class Parser(val s: String) {
        var i = 0

        fun error(msg: String): Nothing = throw IllegalArgumentException("JSON: $msg at $i")

        fun ws() {
            while (i < s.length && s[i].isWhitespace()) i++
        }

        fun value(): Any? {
            ws()
            if (i >= s.length) error("unexpected end")
            return when (s[i]) {
                '{' -> obj()
                '[' -> arr()
                '"' -> str()
                't' -> lit("true", true)
                'f' -> lit("false", false)
                'n' -> lit("null", null)
                else -> number()
            }
        }

        fun lit(word: String, v: Any?): Any? {
            if (!s.startsWith(word, i)) error("bad literal")
            i += word.length
            return v
        }

        fun number(): Double {
            val start = i
            while (i < s.length && (s[i].isDigit() || s[i] in "+-.eE")) i++
            return s.substring(start, i).toDoubleOrNull() ?: error("bad number")
        }

        fun str(): String {
            i++
            val sb = StringBuilder()
            while (true) {
                if (i >= s.length) error("unterminated string")
                val c = s[i++]
                when (c) {
                    '"' -> return sb.toString()
                    '\\' -> {
                        val e = s[i++]
                        when (e) {
                            '"', '\\', '/' -> sb.append(e)
                            'b' -> sb.append('\b')
                            'f' -> sb.append('\u000C')
                            'n' -> sb.append('\n')
                            'r' -> sb.append('\r')
                            't' -> sb.append('\t')
                            'u' -> {
                                sb.append(s.substring(i, i + 4).toInt(16).toChar())
                                i += 4
                            }
                            else -> error("bad escape")
                        }
                    }
                    else -> sb.append(c)
                }
            }
        }

        fun arr(): List<Any?> {
            i++
            val out = ArrayList<Any?>()
            ws()
            if (s[i] == ']') {
                i++
                return out
            }
            while (true) {
                out += value()
                ws()
                when (s[i++]) {
                    ',' -> continue
                    ']' -> return out
                    else -> error("expected , or ]")
                }
            }
        }

        fun obj(): Map<String, Any?> {
            i++
            val out = LinkedHashMap<String, Any?>()
            ws()
            if (s[i] == '}') {
                i++
                return out
            }
            while (true) {
                ws()
                if (s[i] != '"') error("expected key")
                val k = str()
                ws()
                if (s[i++] != ':') error("expected :")
                out[k] = value()
                ws()
                when (s[i++]) {
                    ',' -> continue
                    '}' -> return out
                    else -> error("expected , or }")
                }
            }
        }
    }
}

/** Something with a JSON wire form. */
interface JsonValue {
    fun toJson(): Map<String, Any?>
}
