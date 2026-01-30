"""
Question/Answer Database Loader

Loads and parses the Q&A database for human-readable verification tests.
"""

from pathlib import Path
from typing import List, Optional

import yaml

from .models import (
    DataPoint,
    ExpectedValue,
    Question,
    QuestionDatabase,
    VerificationQuery,
    VerificationType,
)


class QuestionLoader:
    """
    Loads questions from YAML Q&A database files.

    Questions are converted to DataPoint objects for verification.
    """

    def __init__(self, questions_dir: Optional[Path] = None):
        """
        Initialize the question loader.

        Args:
            questions_dir: Directory containing question YAML files.
        """
        self.questions_dir = questions_dir or self._default_questions_dir()

    def _default_questions_dir(self) -> Path:
        """Get the default questions directory."""
        return Path(__file__).parent / "fixtures"

    def load_all(self) -> List[Question]:
        """Load all questions from all YAML files."""
        questions = []

        if not self.questions_dir.exists():
            return questions

        # Load from model-questions.yaml specifically
        questions_file = self.questions_dir / "model-questions.yaml"
        if questions_file.exists():
            db = self._load_questions_file(questions_file)
            if db:
                questions.extend(db.questions)

        return questions

    def _load_questions_file(self, path: Path) -> Optional[QuestionDatabase]:
        """Load a single questions file."""
        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)

            if not data:
                return None

            questions = []
            for q_data in data.get("questions", []):
                question = self._parse_question(q_data)
                if question:
                    questions.append(question)

            return QuestionDatabase(
                questions=questions,
                file_path=str(path)
            )
        except Exception as e:
            print(f"Error loading questions from {path}: {e}")
            return None

    def _parse_question(self, data: dict) -> Optional[Question]:
        """Parse a question from YAML data."""
        try:
            # Parse query
            query_data = data.get("query", {})
            query = VerificationQuery(
                node_id=query_data.get("node_id"),
                node_type=query_data.get("node_type"),
                source_id=query_data.get("source_id"),
                edge_id=query_data.get("edge_id"),
                edge_type=query_data.get("edge_type"),
                source_node_id=query_data.get("source_node_id"),
                target_node_id=query_data.get("target_node_id"),
                label_contains=query_data.get("label_contains"),
                type=query_data.get("type"),
            )

            # Parse answer
            answer_data = data.get("answer", {})
            answer = ExpectedValue(
                exists=answer_data.get("exists"),
                type=answer_data.get("type"),
                label=answer_data.get("label"),
                count=answer_data.get("count"),
                min_count=answer_data.get("min_count"),
                max_count=answer_data.get("max_count"),
                properties=answer_data.get("properties"),
                content_contains=answer_data.get("content_contains"),
                source_node_id=answer_data.get("source_node_id"),
                target_node_id=answer_data.get("target_node_id"),
                edge_type=answer_data.get("edge_type"),
            )

            return Question(
                id=data.get("id", "unknown"),
                question=data.get("question", ""),
                category=data.get("category", "general"),
                query=query,
                answer=answer,
                tags=data.get("tags", [])
            )
        except Exception as e:
            print(f"Error parsing question: {e}")
            return None

    def to_data_points(
        self,
        questions: Optional[List[Question]] = None,
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None
    ) -> List[DataPoint]:
        """
        Convert questions to DataPoint objects for verification.

        Args:
            questions: List of questions (loads all if not provided).
            categories: Optional list of categories to filter by.
            tags: Optional list of tags to filter by.

        Returns:
            List of DataPoint objects.
        """
        if questions is None:
            questions = self.load_all()

        data_points = []
        for q in questions:
            # Filter by category
            if categories and q.category not in categories:
                continue

            # Filter by tags
            if tags and not any(t in q.tags for t in tags):
                continue

            # Determine verification type from query type
            query_type = q.query.type or "node_exists"
            try:
                ver_type = VerificationType(query_type)
            except ValueError:
                ver_type = VerificationType.NODE_EXISTS

            dp = DataPoint(
                id=f"q-{q.id}",
                type=ver_type,
                description=q.question,
                query=q.query,
                expected=q.answer,
                tags=q.tags + [q.category],
                source_file="model-questions.yaml"
            )
            data_points.append(dp)

        return data_points


def load_questions(
    questions_dir: Optional[Path] = None,
    categories: Optional[List[str]] = None,
    tags: Optional[List[str]] = None
) -> List[DataPoint]:
    """
    Convenience function to load questions as DataPoints.

    Args:
        questions_dir: Directory containing question YAML files.
        categories: Optional list of categories to filter by.
        tags: Optional list of tags to filter by.

    Returns:
        List of DataPoint objects.
    """
    loader = QuestionLoader(questions_dir)
    return loader.to_data_points(categories=categories, tags=tags)
