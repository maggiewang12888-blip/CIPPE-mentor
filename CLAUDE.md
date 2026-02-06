# CLAUDE.md — CIPP/E Exam Practice System

## Project Overview

A browser-based **CIPP/E (Certified Information Privacy Professional/Europe) exam practice system** with note-taking functionality. The entire application is a single self-contained HTML file (`CIPP-E刷题系统-带笔记功能.html`) — approximately 6,990 lines / 735 KB. All UI text and question content are in **Simplified Chinese**.

### Key Features
- **289 practice questions** covering GDPR, ECHR, and European privacy law
- **Practice Mode**: Sequential question practice with auto-skip for completed questions
- **Exam Mode**: 90-question simulated exam (75 scored + 15 unscored test questions), 150-minute timer, scaled scoring (100–500, passing = 300)
- **Review Mode**: Focused study on previously incorrect answers
- **Notes**: Per-question notes with auto-save to localStorage
- **Progress Tracking**: Accuracy, completion rate, and attempt statistics persisted in localStorage

## Technology Stack

| Layer | Technology |
|-------|-----------|
| UI Framework | React 18 (production CDN build) |
| JSX Transpilation | Babel Standalone (CDN) |
| CSS | Tailwind CSS (CDN) |
| State Management | React Hooks (`useState`, `useEffect`, `useMemo`) |
| Data Persistence | Browser `localStorage` |
| Icons | Custom inline SVG components |

All dependencies load from CDN (`unpkg.com`, `cdn.tailwindcss.com`). There is **no build system, no package.json, no bundler, no Node.js tooling**.

## File Structure

```
CIPPE-mentor/
├── CLAUDE.md                              # This file
├── CIPP-E刷题系统-带笔记功能.html          # Entire application (single file)
└── .git/                                  # Git repository
```

### HTML File Internal Structure

The single HTML file is organized as follows:

| Section | Lines (approx.) | Content |
|---------|-----------------|---------|
| `<head>` | 1–10 | CDN imports (React, Babel, Tailwind) |
| `<style>` | 11–120 | Custom CSS animations (`fade-in`, `slide-down`, `pulse`, `shake`) and base styles |
| `<script id="questions-data">` | ~130–5900 | Embedded JSON array with 289 question objects |
| `<script type="text/babel">` | ~5900–6988 | React application code (JSX) |
| SVG icon components | ~5900–5967 | `BookOpen`, `Trophy`, `Target`, `CheckCircle`, `XCircle`, `BarChart`, etc. |
| `CIPPEQuizApp` component | 5969–6985 | Main application component |
| `ReactDOM.render(...)` | 6987 | App mounting |

## Application Architecture

### Main Component: `CIPPEQuizApp` (line 5969)

Single functional component managing all application state via 15 `useState` hooks:

**Core state:**
- `questions` — Full question database (loaded from embedded JSON)
- `mode` — Current view: `'home'` | `'practice'` | `'exam'` | `'review'`
- `currentQuestionIndex` — Active question pointer
- `selectedAnswer` / `showExplanation` — Answer interaction state

**Progress state:**
- `practiceProgress` — Object mapping question ID to attempt history
- `completedQuestions` — `Set` of completed question IDs
- `totalAttempts` — Cumulative attempt counter

**Exam state:**
- `examQuestions` / `examAnswers` / `examSubmitted` / `examResults`
- `examTimeRemaining` / `examStartTime` — Timer state
- `testQuestionIds` — `Set` of 15 unscored "test" question IDs

**Notes state:**
- `myNotes` — Object mapping question ID to note text

### Question Data Schema

```javascript
{
  id: number,            // Unique question ID (1-289)
  scenario: string,      // Optional context/scenario text
  question: string,      // Question text
  options: string[],     // Array of 4 answer options
  correctAnswer: number, // Index (0-3) of correct option
  explanation: string,   // Detailed explanation
  optionExplanations: string[], // Per-option analysis
  legalReference: string // Legal basis (e.g., "GDPR Article 6")
}
```

### localStorage Keys

| Key | Type | Purpose |
|-----|------|---------|
| `cipp-e-progress` | JSON object | Per-question attempt history |
| `cipp-e-completed` | JSON array | IDs of completed questions |
| `cipp-e-total-attempts` | integer string | Cumulative attempt count |
| `question-notes` | JSON object | Per-question notes (keyed by ID) |

### Key Navigation Functions

- `startPractice()` — Begin practice, skip already-completed questions
- `startExam()` — Shuffle questions, select 90, designate 15 as unscored test questions
- `startReview()` — Filter to only incorrectly-answered questions
- `nextQuestion()` / `prevQuestion()` — Navigate with bounds checking
- `goHome()` — Reset state, return to home screen

### Exam Scoring Logic

- Raw percentage: `(correct / scoredQuestions) × 100`
- Scaled score: `100 + (rawPercentage × 4)` → range 100–500
- Passing threshold: **≥ 300 points**
- 15 randomly selected "test" questions are excluded from scoring

## Development Guidelines

### How to Run
Open `CIPP-E刷题系统-带笔记功能.html` directly in a web browser. Internet connection required for CDN dependencies.

### How to Modify

Since this is a single-file application with no build step:
1. Edit the HTML file directly
2. Refresh the browser to see changes
3. The React code is in `<script type="text/babel">` — Babel transpiles JSX in-browser

### Important Conventions

- **Single-file architecture**: All code, styles, and data live in one HTML file. Do not split into multiple files without explicit instruction.
- **No build tools**: There is no npm, webpack, Vite, or any build pipeline. Changes take effect on browser reload.
- **Embedded question data**: The 289-question JSON dataset is embedded directly in a `<script id="questions-data" type="application/json">` tag. When adding/modifying questions, edit this JSON block.
- **Chinese language**: All UI strings, question text, and explanations are in Simplified Chinese. Maintain this convention.
- **Tailwind utility classes**: Styling uses Tailwind CSS utility classes inline. No custom CSS class names except for animations.
- **localStorage for persistence**: All user data is stored client-side. There is no backend or database.

### UI/Design Patterns

- **Color theme**: Blue-purple-pink gradients (`from-blue-600 via-purple-600 to-pink-500`)
- **Glassmorphism**: Cards use `backdrop-blur` with semi-transparent backgrounds
- **Animations**: `fade-in`, `slide-down`, `pulse`, and `shake` (for exam time warnings)
- **Responsive layout**: Grid system adapts from 1 to 4 columns based on viewport

### Testing

There are no automated tests. All testing is manual via browser interaction. When making changes:
1. Verify home screen statistics display correctly
2. Test practice mode: question navigation, answer selection, explanation display
3. Test exam mode: timer, question grid, submission, scoring
4. Test review mode: only incorrect questions appear
5. Test notes: adding, editing, persistence across page reloads
6. Verify localStorage persistence (reload page, check data survives)

### Common Pitfalls

- **Large file size**: The file is ~735 KB. Edits require careful line targeting — always use `Read` with offset/limit for specific sections rather than reading the entire file.
- **Embedded JSON**: The question data block spans thousands of lines. When editing questions, ensure valid JSON structure is maintained.
- **No hot reload**: Changes require a full browser refresh.
- **CDN dependency**: The app will not work offline since React, Babel, and Tailwind load from CDNs.
- **localStorage limits**: Browser localStorage is typically limited to 5–10 MB. The current data footprint is well within limits but be aware when adding features.
