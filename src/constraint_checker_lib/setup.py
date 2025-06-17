from setuptools import setup, find_packages

setup(
    name="constraints_checker",
    version="0.1.0",
    description="A library for managing synchronous and asynchronous DSL-based constraints execution.",
    author="cognitifai",
    author_email="",
    url="",  # Replace with your GitHub URL or project link
    packages=find_packages(exclude=["tests*", "examples*"]),
    install_requires=[
        "requests", 
    ],
    python_requires=">=3.7", 
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    keywords="constraints, DSL, multiprocessing, asynchronous",
   
)
