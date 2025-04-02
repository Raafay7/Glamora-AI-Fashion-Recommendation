document.addEventListener('DOMContentLoaded', function() {
    // Quiz questions and options
    const quizData = [
      {
        question: "What types of clothes are you looking for?",
        options: ["Casual", "Workwear", "Social occasions", "Maternity"],
        type: "radio"
      },
      {
        question: "How tall are you?",
        options: ["Under 5'2\" (Petite)", "5'3\" - 5'6\" (Average)", "5'7\" - 5'10\" (Tall)", "Above 5'10\""],
        type: "radio"
      },
      {
        question: "What is your body shape?",
        options: ["Hourglass – Waist is the narrowest part of the frame", 
                  "Triangle – Hips are broader than shoulders", 
                  "Rectangle – Hips, shoulders, and waist are the same proportion", 
                  "Oval – Hips and shoulders are narrower than waist", 
                  "Heart – Hips are narrower than shoulders"],
        type: "radio"
      },
      {
        question: "What is your skin tone?",
        options: ["Light (Very fair or pale)", 
                  "Wheatish (Fair with warm undertones)", 
                  "Medium Tan (Moderate brown with neutral undertones)", 
                  "Deep Brown (Dark complexion)"],
        type: "radio"
      },
      {
        question: "What is your hair color?",
        options: ["Black", "Brown", "Dyed (Blonde, Red, Balayage, etc.)"],
        type: "radio"
      },
      {
        question: "What is your usual clothing size in Pakistani brands?",
        options: ["XS", "S", "M", "L", "XL", "XXL+"],
        type: "radio"
      },
      {
        question: "Do you have any favorite Pakistani fashion brands? (Optional)",
        options: ["Khaadi", "Gul Ahmed", "Sapphire", "Generation", "Maria B"],
        type: "checkbox"
      },
      {
        question: "What is your usual budget range for clothing?",
        options: ["Budget (Affordable brands, local markets)", 
                  "Mid-range (High-street brands like Sapphire, Khaadi)", 
                  "Premium (Luxury brands like Élan, Sania Maskatiya)"],
        type: "radio"
      }
    ];
  
    // Initialize variables
    let currentQuestion = 0;
    const answers = {};
    const questionContainer = document.getElementById('question-container');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const submitBtn = document.getElementById('submit-btn');
    const quizProgress = document.getElementById('quiz-progress');
    const currentQuestionSpan = document.getElementById('current-question');
    const totalQuestionsSpan = document.getElementById('total-questions');
  
    // Set total questions number
    totalQuestionsSpan.textContent = quizData.length;
  
    // Load first question
    loadQuestion();
  
    // Add event listeners to buttons
    prevBtn.addEventListener('click', goToPrevQuestion);
    nextBtn.addEventListener('click', goToNextQuestion);
    submitBtn.addEventListener('click', submitQuiz);
  
    // Function to load a question
    function loadQuestion() {
      // Update progress bar
      updateProgress();
      
      // Get current question data
      const currentQuizData = quizData[currentQuestion];
      
      // Create question element
      const questionElement = document.createElement('div');
      questionElement.classList.add('question-slide');
      questionElement.setAttribute('data-question', currentQuestion);
      
      // Add question title
      const questionTitle = document.createElement('h2');
      questionTitle.classList.add('question-title');
      questionTitle.textContent = currentQuizData.question;
      questionElement.appendChild(questionTitle);
      
      // Add options
      const optionsContainer = document.createElement('div');
      optionsContainer.classList.add('options-container');
      
      currentQuizData.options.forEach((option, index) => {
        const optionContainer = document.createElement('div');
        optionContainer.classList.add('option');
        
        const input = document.createElement('input');
        input.type = currentQuizData.type;
        input.id = `q${currentQuestion}-option${index}`;
        input.name = `question${currentQuestion}`;
        input.value = option;
        
        // Check if this option was previously selected
        if (currentQuizData.type === 'radio' && answers[currentQuestion] === option) {
          input.checked = true;
        } else if (currentQuizData.type === 'checkbox' && 
                   answers[currentQuestion] && 
                   answers[currentQuestion].includes(option)) {
          input.checked = true;
        }
        
        const label = document.createElement('label');
        label.htmlFor = `q${currentQuestion}-option${index}`;
        label.textContent = option;
        
        optionContainer.appendChild(input);
        optionContainer.appendChild(label);
        optionsContainer.appendChild(optionContainer);
        
        // Add event listener to save answer when selected
        input.addEventListener('change', function() {
          saveAnswer();
        });
      });
      
      questionElement.appendChild(optionsContainer);
      
      // Clear previous question and add new one
      questionContainer.innerHTML = '';
      questionContainer.appendChild(questionElement);
      
      // Update button states
      updateButtonStates();
    }
  
    // Function to save the current answer
    function saveAnswer() {
      const currentQuizData = quizData[currentQuestion];
      
      if (currentQuizData.type === 'radio') {
        const selectedOption = document.querySelector(`input[name="question${currentQuestion}"]:checked`);
        if (selectedOption) {
          answers[currentQuestion] = selectedOption.value;
        }
      } else if (currentQuizData.type === 'checkbox') {
        const selectedOptions = document.querySelectorAll(`input[name="question${currentQuestion}"]:checked`);
        answers[currentQuestion] = Array.from(selectedOptions).map(option => option.value);
      }
    }
  
    // Function to go to the next question
    function goToNextQuestion() {
      saveAnswer();
      currentQuestion++;
      currentQuestionSpan.textContent = currentQuestion + 1;
      
      if (currentQuestion >= quizData.length - 1) {
        nextBtn.style.display = 'none';
        submitBtn.style.display = 'block';
      }
      
      loadQuestion();
    }
  
    // Function to go to the previous question
    function goToPrevQuestion() {
      saveAnswer();
      currentQuestion--;
      currentQuestionSpan.textContent = currentQuestion + 1;
      
      if (currentQuestion < quizData.length - 1) {
        nextBtn.style.display = 'block';
        submitBtn.style.display = 'none';
      }
      
      loadQuestion();
    }
  
    // Function to update button states
    function updateButtonStates() {
      prevBtn.disabled = currentQuestion === 0;
      currentQuestionSpan.textContent = currentQuestion + 1;
    }
  
    // Function to update progress bar
    function updateProgress() {
      const progressPercentage = ((currentQuestion + 1) / quizData.length) * 100;
      quizProgress.style.width = `${progressPercentage}%`;
    }
  
    // Function to submit the quiz
    function submitQuiz() {
      saveAnswer();
      
      // Prepare data for submission
      const formData = new FormData();
      
      // Add answers to form data
      for (let i = 0; i < quizData.length; i++) {
        const question = quizData[i].question;
        let answer = answers[i];
        
        if (Array.isArray(answer)) {
          answer = answer.join(', ');
        }
        
        formData.append(`question_${i}`, question);
        formData.append(`answer_${i}`, answer || '');
      }
      
      // Get CSRF token
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
      
      // Submit data using fetch
      fetch('/save-style-quiz/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken
        },
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          // Show success message or redirect
          window.location.href = '/login/';
        } else {
          alert('There was an error saving your preferences. Please try again.');
        }
      })
      .catch(error => {
        console.error('Error:', error);
        alert('There was an error submitting the quiz. Please try again.');
      });
    }
  });