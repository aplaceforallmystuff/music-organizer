# Contributing to Music Organizer

Thank you for your interest in contributing to Music Organizer!

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR-USERNAME/music-organizer.git
   cd music-organizer
   ```
3. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e ".[dev]"
   ```
4. Create a branch for your changes:
   ```bash
   git checkout -b feat/your-feature-name
   ```

## Development

### Running Tests

```bash
pytest
```

### Code Style

This project follows standard Python conventions:
- Use type hints where practical
- Follow PEP 8 guidelines
- Keep functions focused and well-documented

### Project Structure

```
music-organizer/
├── src/
│   └── music_organizer/
│       ├── __init__.py
│       ├── cli.py          # Command-line interface
│       ├── organizer.py    # Core organization logic
│       ├── metadata.py     # Metadata extraction
│       ├── cache.py        # Scan caching
│       └── ...
├── tests/
├── pyproject.toml
└── README.md
```

## Submitting Changes

1. Commit your changes using conventional commit format:
   ```
   feat(metadata): add support for OPUS files
   fix(cache): handle corrupted cache file gracefully
   docs: update installation instructions
   ```

2. Push to your fork and submit a pull request

3. Ensure your PR description explains:
   - What the change does
   - Why it's needed
   - How to test it

## Reporting Issues

When reporting bugs, please include:
- Python version (`python --version`)
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Any error messages

## Questions?

Feel free to open an issue for questions or discussion.
