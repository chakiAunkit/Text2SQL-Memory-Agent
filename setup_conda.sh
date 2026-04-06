#!/bin/bash
# Quick Setup Script for Text2SQL with Conda
# Run this after cloning the repository

set -e  # Exit on error

echo "🚀 Text2SQL with Long-Term Memory - Conda Setup"
echo "================================================"
echo ""

# Check if conda is installed
if ! command -v conda &> /dev/null; then
    echo "❌ Error: conda not found. Please install Anaconda or Miniconda first."
    echo "   Download from: https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

echo "✅ Conda found: $(conda --version)"
echo ""

# Create conda environment from Python version + pip-install the project
ENV_NAME="text2sql-memory"

if conda env list | grep -q "^${ENV_NAME} "; then
    echo "⚠️  Environment '${ENV_NAME}' already exists."
    read -p "Do you want to recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        conda env remove -n "${ENV_NAME}"
        conda create -n "${ENV_NAME}" python=3.10 -y
    fi
else
    conda create -n "${ENV_NAME}" python=3.10 -y
fi

echo "✅ Conda environment created"
echo ""

# Install project dependencies inside the conda env
echo "📦 Installing dependencies..."
conda run -n "${ENV_NAME}" pip install -e ".[dev,test]"
echo "✅ Dependencies installed"
echo ""

# Activate instructions
echo "🎯 Next Steps:"
echo ""
echo "1. Activate the environment:"
echo "   conda activate ${ENV_NAME}"
echo ""
echo "2. Setup PostgreSQL and load the sample schema:"
echo "   createdb testdb"
echo "   psql -d testdb -f core_logic/test_db_setup.sql"
echo ""
echo "3. Install and start Ollama:"
echo "   # Install: curl -fsSL https://ollama.ai/install.sh | sh"
echo "   ollama serve        # run in a separate terminal"
echo "   ollama pull codellama:7b"
echo ""
echo "4. Configure environment variables:"
echo "   cp core_logic/.env.example core_logic/.env   # then edit with your settings"
echo "   # Required: TARGET_DB_CONNECTION, LLM_BASE_URL, LLM_MODEL"
echo ""
echo "5. Run the application:"
echo "   cd core_logic && python gradio_frontend.py"
echo ""
echo "✨ Setup complete! Happy coding! 🎉"
