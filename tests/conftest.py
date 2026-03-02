"""
Shared fixtures for the test suite.
"""
import os
import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Ensure tests never touch real credentials or external services."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-fake-key")
    monkeypatch.setenv("MONGODB_URI", "")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")


@pytest.fixture
def sample_content():
    """A minimal valid content dict matching LLM output schema."""
    return {
        "title": "Python List Trick #Shorts",
        "script": (
            "Did you know you can flatten a nested list in Python with just one line? "
            "Use a list comprehension with a nested for loop. It's clean, readable, "
            "and way faster than writing a recursive function. Here's how it works "
            "in just three lines of code. Try it out in your next project!"
        ),
        "code": "nested = [[1, 2], [3, 4], [5]]\nflat = [x for sub in nested for x in sub]\nprint(flat)",
        "language": "python",
        "hashtags": ["#Python", "#CodingTips", "#Programming", "#Shorts", "#Dev"],
        "content_type": "tip",
        "expected_output": "",
        "quiz_answer": "",
        "code_before": "",
    }


@pytest.fixture
def sample_content_output_demo():
    """Content dict for output_demo type."""
    return {
        "title": "Python F-String Trick #Shorts",
        "script": (
            "Check this out — Python f-strings can do way more than simple variable insertion. "
            "You can put expressions, method calls, and even format specs right inside the braces. "
            "Watch what happens when we use an f-string to center-align text with padding characters. "
            "This is super useful for building CLI tools and formatted reports."
        ),
        "code": "name = 'Python'\nprint(f'{name:*^20}')",
        "language": "python",
        "hashtags": ["#Python", "#FString", "#CodingTips", "#Shorts", "#Dev"],
        "content_type": "output_demo",
        "expected_output": "*******Python*******",
        "quiz_answer": "",
        "code_before": "",
    }


@pytest.fixture
def sample_content_quiz():
    """Content dict for quiz type."""
    return {
        "title": "What Does This Print? #Shorts",
        "script": (
            "Alright coders, pop quiz! Take a close look at this Python code and tell me "
            "what it prints. Think carefully about how the plus operator works with lists "
            "versus the extend method. The answer might surprise you if you're not paying "
            "attention to mutability. Drop your guess in the comments!"
        ),
        "code": "a = [1, 2, 3]\nb = a\nb += [4]\nprint(a)",
        "language": "python",
        "hashtags": ["#Python", "#CodeQuiz", "#Programming", "#Shorts", "#Dev"],
        "content_type": "quiz",
        "expected_output": "",
        "quiz_answer": "[1, 2, 3, 4] — += on lists mutates in-place",
        "code_before": "",
    }


@pytest.fixture
def sample_content_before_after():
    """Content dict for before_after type."""
    return {
        "title": "Stop Using Range Len #Shorts",
        "script": (
            "If you're still writing for i in range len to loop through a list, stop right now. "
            "Python has a much cleaner way called enumerate. It gives you both the index and the "
            "value in one shot. Your code becomes shorter, more readable, and more Pythonic. "
            "Here's the before and after — see the difference for yourself."
        ),
        "code": "fruits = ['apple', 'banana']\nfor i, f in enumerate(fruits):\n    print(i, f)",
        "language": "python",
        "hashtags": ["#Python", "#CleanCode", "#CodingTips", "#Shorts", "#Dev"],
        "content_type": "before_after",
        "expected_output": "",
        "quiz_answer": "",
        "code_before": "fruits = ['apple', 'banana']\nfor i in range(len(fruits)):\n    print(i, fruits[i])",
    }
