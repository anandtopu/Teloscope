"""AgentLens Python SDK package config."""
from setuptools import setup, find_packages

setup(
    name="agentlens-sdk",
    version="1.0.0",
    description="AgentLens — AI Agent Observability SDK for Python",
    long_description=open("README.md").read() if __import__("os").path.exists("README.md") else "",
    author="AgentLens Contributors",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.28",
        "pydantic>=2.0",
    ],
    extras_require={
        "langchain": ["langchain>=0.3"],
        "openai":    ["openai>=1.0"],
        "anthropic": ["anthropic>=0.30"],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
