# Persona: attention student (for `why attention divides by sqrt(d_k)`)

Played by the person driving `tools/drive.py`. Answer only from this sheet plus what the lesson has
*taught and checked* so far. Read only the visible replies; never look at tool results.

## Background
- Data science student, second year. Comfortable with Python and NumPy.
- Knows matrix multiplication and computes dot products mechanically (sum of products).
- Knows what softmax does to a vector: exponentiate, normalise, rows sum to 1.
- Has seen the attention formula softmax(QK^T / sqrt(d_k)) V and can say what Q, K, V are for, roughly.
- Already holds the facts in the imported graph (softmax ratios, scaling scores sharpens softmax).

## Gaps (each from a real recorded answer)
1. Doesn't know the notation E[·]. If a question uses it unexplained: "I don't know what E is".
2. Believes Var(X+Y) = 1 for independent X, Y each with variance 1 ("they each had variance 1").
3. Knows variance only as "the spread"; no squared-deviation definition; doesn't know Var = E[X²] − E[X]².
4. Aggregating a double sum: computes one representative term correctly and returns it as the total.
5. Reads a weight as a cutoff/threshold rather than a multiplier.
6. Vague on why large scores hurt training ("it gets bigger?"); no idea about softmax gradients.

## How he answers
- Short, informal, some typos. Often no LaTeX.
- Confidence: often 30%; 0% when guessing; 50-70% only when he really reasoned it. Sometimes forgets it.
- MC: gives the letter, sometimes with a one-line reason. Free answers: one to three sentences.
- Sometimes "I don't know", sometimes answers a slightly different question than asked.
- If a question is genuinely unclear to him, he says so.
- Plan approval: reads it, says "looks good" unless something is clearly off for him.

## How he learns
- Probe: learns nothing, even if the model explains. Keep answering from the sheet.
- Teaching: a step he is taught clearly and then checked on, he gets right next time (~70%), or half-right
  (~30%, a plausible partial misunderstanding). He never knows more than he has been taught.
- Confidence rises (to 70) once a step clicks.
