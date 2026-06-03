# Grep vs Raw Context — Side by side

Same question: "Where is Mary?" Same text: 965,000 characters. Same model: gpt-5.4-mini.

---

## Raw Context Injection (cbench)

| Step | What happens | Chars |
|---|---|---|
| 1 | Chunk 1/18 injected. Model: "OK." | 62,580 |
| 2 | Chunk 2/18 injected. Model: "OK." | 59,057 |
| 3 | Chunk 3/18 injected. Model: "OK." | 57,773 |
| 4 | Chunk 4/18 injected. Model: "OK." | 61,016 |
| 5 | Chunk 5/18 injected. Model: "OK." | 54,396 |
| 6 | Chunk 6/18 injected. Model: "OK." | 60,063 |
| 7 | Chunk 7/18 injected. Model: "OK." | 50,319 |
| 8 | Chunk 8/18 injected. Model: "OK." | 59,999 |
| ... | (codex auto-compacts silently here) | |
| 9-18 | Remaining chunks injected. "OK." | ~55k each |
| 19 | "Now answer. Do not use tools." | |
| 20 | Model: "the bathroom" ✓ | |

Total: 38 turns. 2 compactions. ~965k chars processed. Answer correct.

---

## Grep (codex exec)

| Step | What happens | Command |
|---|---|---|
| 1 | Try grep. File not found. | `grep -n -C 2 -i 'Mary' /tmp/full_context.txt` → No such file |
| 2 | Find the file. | `ls -la /tmp` → symlink to /private/tmp |
| 3 | List directory. | `ls -la /private/tmp` → found grep_full_exp |
| 4 | Locate exact file. | `find /private/tmp -name 'full_context.txt'` → found |
| 5 | Grep for Mary. | `grep -n -i -C 2 'Mary' ...` → line 4681 found |
| 6 | Verify context. | `sed -n '4668,4686p' ...` → confirmed sentence |
| 7 | Check for multiple Marys. | `grep -n -i '\bMary\b' ...` → only one |
| 8 | Answer. | "bathroom" ✓ |

Total: 7 commands. 0 compactions. Model searched 965k chars but only read ~200 chars of grep output. Answer correct.

---

## The real difference

| | Raw context | Grep |
|---|---|---|
| Turns | 38 | 8 |
| Compactions | 2 | 0 |
| Text processed by model | ~965,000 chars | ~200 chars (grep output) |
| Model can use tools | No | Yes |
| Error recovery | No | Yes (file not found → find) |
| Verification | No | Yes (sed, second grep) |

Both got the correct answer on this task. But the mechanism is completely different. Context injection relies on the model's memory surviving compaction. Grep relies on the model's ability to search a file. When compaction fails (as it does 40% of the time on harder tasks), grep still works because it never touches the full text.
