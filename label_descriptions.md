* **Judge failure:** The model provides an acceptable answer, but the evaluator incorrectly marks it wrong despite a valid reference answer. Examples include rejecting equivalent expressions or valid alternative answers.

* **Incorrect reference answer:** The benchmark’s reference answer is factually or mathematically incorrect, or excludes other demonstrably valid answers. Identify evidence that the reference is defective; disagreement with the model alone is insufficient.

* **Tool or environment failure:** A malfunctioning or unavailable tool, inaccessible resource, or execution-environment problem prevents successful completion. Excludes model errors in selecting or using a functioning tool.

* **Resource limit:** An enforced token, time, context, or tool-call limit prevents completion. Require evidence that the limit was reached and materially affected the attempt.

* **Answer-format failure:** The model provides the substantively correct answer but fails to follow an explicit output-format requirement, causing rejection or extraction failure.

* **Ambiguous or defective prompt:** Ambiguity, missing information, contradictory requirements, or faulty premises prevent a uniquely defensible answer or support the model’s alternative interpretation.

* **Reasoning failure:** The model makes an identifiable error in inference, calculation, planning, or applying available information. Identify the erroneous step and how it contributes to the incorrect answer.

* **Knowledge failure:** The model lacks, misrecalls, or fabricates a fact, definition, or domain-specific rule needed to solve the task. Identify the specific knowledge gap or factual error.

Assign the most directly supported primary category, noting secondary categories when relevant. Cite evidence from the available record. If no specific cause is supported, report “undetermined”; do not infer reasoning or knowledge failure solely from an incorrect final answer.
