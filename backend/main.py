import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import create_engine, text, Column, String, Integer, Float, DateTime, Text, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session, relationship
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import enum

PORT = int(os.environ.get("COMPANY_PORT", 8000))
DATABASE_URL = os.environ.get("DATABASE_URL", "")
COMPANY_SLUG = re.sub(r"[^a-z0-9_]", "_", os.environ.get("COMPANY_SLUG", "talentpipe").lower())
db_engine = None
SessionLocal = None

class Base(DeclarativeBase):
    pass

if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    db_engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"options": f"-csearch_path={COMPANY_SLUG},public"},
    )
    SessionLocal = sessionmaker(bind=db_engine)
    with db_engine.connect() as _conn:
        _conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{COMPANY_SLUG}"'))
        _conn.commit()

class ApplicationStatus(str, enum.Enum):
    NEW = "new"
    SCREENING = "screening"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    INTERVIEWED = "interviewed"
    OFFERED = "offered"
    HIRED = "hired"
    REJECTED = "rejected"

class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": COMPANY_SLUG}
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, default="recruiter")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = {"schema": COMPANY_SLUG}
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String)
    current_company = Column(String)
    current_role = Column(String)
    years_experience = Column(Float)
    skills = Column(Text)
    resume_text = Column(Text)
    resume_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    source = Column(String, default="direct")

class JobRequirement(Base):
    __tablename__ = "job_requirements"
    __table_args__ = {"schema": COMPANY_SLUG}
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    department = Column(String)
    location = Column(String)
    employment_type = Column(String, default="full-time")
    min_experience = Column(Float)
    required_skills = Column(Text)
    description = Column(Text)
    salary_range_min = Column(Float)
    salary_range_max = Column(Float)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    hiring_manager_id = Column(String, ForeignKey(f"{COMPANY_SLUG}.users.id"))
    hiring_manager = relationship("User")

class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = {"schema": COMPANY_SLUG}
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id = Column(String, ForeignKey(f"{COMPANY_SLUG}.candidates.id"), nullable=False)
    job_requirement_id = Column(String, ForeignKey(f"{COMPANY_SLUG}.job_requirements.id"), nullable=False)
    raw_text = Column(Text)
    parsed_skills = Column(Text)
    match_score = Column(Float)
    is_shortlisted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    candidate = relationship("Candidate")
    job_requirement = relationship("JobRequirement")

class Interview(Base):
    __tablename__ = "interviews"
    __table_args__ = {"schema": COMPANY_SLUG}
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id = Column(String, ForeignKey(f"{COMPANY_SLUG}.candidates.id"), nullable=False)
    job_requirement_id = Column(String, ForeignKey(f"{COMPANY_SLUG}.job_requirements.id"), nullable=False)
    interviewer_id = Column(String, ForeignKey(f"{COMPANY_SLUG}.users.id"), nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, default=60)
    interview_type = Column(String, default="technical")
    status = Column(String, default="scheduled")
    notes = Column(Text)
    feedback_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    candidate = relationship("Candidate")
    job_requirement = relationship("JobRequirement")
    interviewer = relationship("User")

class Application(Base):
    __tablename__ = "applications"
    __table_args__ = {"schema": COMPANY_SLUG}
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id = Column(String, ForeignKey(f"{COMPANY_SLUG}.candidates.id"), nullable=False)
    job_requirement_id = Column(String, ForeignKey(f"{COMPANY_SLUG}.job_requirements.id"), nullable=False)
    status = Column(SAEnum(ApplicationStatus), default=ApplicationStatus.NEW)
    resume_id = Column(String, ForeignKey(f"{COMPANY_SLUG}.resumes.id"))
    match_score = Column(Float)
    applied_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    candidate = relationship("Candidate")
    job_requirement = relationship("JobRequirement")
    resume = relationship("Resume")

if db_engine:
    Base.metadata.create_all(db_engine)

def get_db():
    if not SessionLocal:
        raise HTTPException(status_code=503, detail="Database not available")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _seed_if_empty(db: Session):
    if db.query(User).count() == 0:
        users = [
            User(id=str(uuid.uuid4()), email="sarah@talentpipe.io", name="Sarah Chen", role="admin"),
            User(id=str(uuid.uuid4()), email="marcus@talentpipe.io", name="Marcus Johnson", role="recruiter"),
            User(id=str(uuid.uuid4()), email="emily@talentpipe.io", name="Emily Rodriguez", role="hiring_manager"),
        ]
        db.add_all(users)
        db.commit()

        candidates = [
            Candidate(name="Alex Thompson", email="alex.t@example.com", phone="+1-555-0101", current_company="TechStart Inc", current_role="Senior Software Engineer", years_experience=7, skills="Python, React, AWS, Docker, Kubernetes", resume_text="Senior engineer with 7 years experience building scalable applications"),
            Candidate(name="Priya Patel", email="priya.p@example.com", phone="+1-555-0102", current_company="DataFlow Corp", current_role="Data Scientist", years_experience=5, skills="Python, R, TensorFlow, SQL, Machine Learning", resume_text="Data scientist specializing in NLP and predictive modeling"),
            Candidate(name="James Wilson", email="james.w@example.com", phone="+1-555-0103", current_company="CloudBase", current_role="DevOps Engineer", years_experience=4, skills="AWS, Terraform, Jenkins, Docker, Linux", resume_text="DevOps engineer experienced in cloud infrastructure automation"),
            Candidate(name="Lisa Kim", email="lisa.k@example.com", phone="+1-555-0104", current_company="InnoTech", current_role="Product Manager", years_experience=6, skills="Product Strategy, Agile, Analytics, UX Design", resume_text="Product manager with strong technical background and user focus"),
            Candidate(name="Carlos Mendez", email="carlos.m@example.com", phone="+1-555-0105", current_company="WebDev Pro", current_role="Full Stack Developer", years_experience=3, skills="JavaScript, Node.js, Vue.js, MongoDB, GraphQL", resume_text="Full stack developer building modern web applications"),
        ]
        db.add_all(candidates)
        db.commit()

        jobs = [
            JobRequirement(title="Senior Software Engineer", department="Engineering", location="San Francisco, CA", min_experience=5, required_skills="Python, React, AWS, System Design", description="Build and scale our AI-powered recruitment platform", salary_range_min=150000, salary_range_max=220000, hiring_manager_id=users[2].id),
            JobRequirement(title="Data Scientist", department="AI/ML", location="Remote", min_experience=3, required_skills="Python, Machine Learning, NLP, SQL", description="Develop ML models for resume parsing and candidate matching", salary_range_min=130000, salary_range_max=190000, hiring_manager_id=users[0].id),
            JobRequirement(title="DevOps Engineer", department="Infrastructure", location="New York, NY", min_experience=3, required_skills="AWS, Docker, Kubernetes, CI/CD", description="Maintain and scale cloud infrastructure for growing platform", salary_range_min=120000, salary_range_max=175000, hiring_manager_id=users[2].id),
        ]
        db.add_all(jobs)
        db.commit()

        resumes = [
            Resume(candidate_id=candidates[0].id, job_requirement_id=jobs[0].id, raw_text=candidates[0].resume_text, parsed_skills="Python, React, AWS, Docker, Kubernetes", match_score=92.5, is_shortlisted=True),
            Resume(candidate_id=candidates[1].id, job_requirement_id=jobs[1].id, raw_text=candidates[1].resume_text, parsed_skills="Python, R, TensorFlow, SQL, Machine Learning", match_score=88.3, is_shortlisted=True),
            Resume(candidate_id=candidates[2].id, job_requirement_id=jobs[2].id, raw_text=candidates[2].resume_text, parsed_skills="AWS, Terraform, Jenkins, Docker, Linux", match_score=85.7, is_shortlisted=True),
            Resume(candidate_id=candidates[3].id, job_requirement_id=jobs[0].id, raw_text=candidates[3].resume_text, parsed_skills="Product Strategy, Agile, Analytics, UX Design", match_score=45.2, is_shortlisted=False),
            Resume(candidate_id=candidates[4].id, job_requirement_id=jobs[0].id, raw_text=candidates[4].resume_text, parsed_skills="JavaScript, Node.js, Vue.js, MongoDB, GraphQL", match_score=62.8, is_shortlisted=False),
        ]
        db.add_all(resumes)
        db.commit()

        now = datetime.utcnow()
        interviews = [
            Interview(candidate_id=candidates[0].id, job_requirement_id=jobs[0].id, interviewer_id=users[2].id, scheduled_at=now + timedelta(days=2), interview_type="technical", status="scheduled"),
            Interview(candidate_id=candidates[1].id, job_requirement_id=jobs[1].id, interviewer_id=users[0].id, scheduled_at=now + timedelta(days=3), interview_type="technical", status="scheduled"),
            Interview(candidate_id=candidates[2].id, job_requirement_id=jobs[2].id, interviewer_id=users[2].id, scheduled_at=now + timedelta(days=4), interview_type="system_design", status="scheduled"),
        ]
        db.add_all(interviews)
        db.commit()

        applications = [
            Application(candidate_id=candidates[0].id, job_requirement_id=jobs[0].id, status=ApplicationStatus.INTERVIEW_SCHEDULED, resume_id=resumes[0].id, match_score=92.5),
            Application(candidate_id=candidates[1].id, job_requirement_id=jobs[1].id, status=ApplicationStatus.INTERVIEW_SCHEDULED, resume_id=resumes[1].id, match_score=88.3),
            Application(candidate_id=candidates[2].id, job_requirement_id=jobs[2].id, status=ApplicationStatus.SCREENING, resume_id=resumes[2].id, match_score=85.7),
            Application(candidate_id=candidates[3].id, job_requirement_id=jobs[0].id, status=ApplicationStatus.NEW, resume_id=resumes[3].id, match_score=45.2),
            Application(candidate_id=candidates[4].id, job_requirement_id=jobs[0].id, status=ApplicationStatus.REJECTED, resume_id=resumes[4].id, match_score=62.8),
        ]
        db.add_all(applications)
        db.commit()
        print(f"[{COMPANY_SLUG}] Seeded initial data")

if db_engine:
    with SessionLocal() as db:
        _seed_if_empty(db)

app = FastAPI(title="TalentPipe", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok", "schema": COMPANY_SLUG, "db": db_engine is not None}

@app.get("/api/info")
def company_info():
    return {
        "name": "TalentPipe",
        "tagline": "AI-powered recruitment for growing companies",
        "description": "Automate your hiring pipeline with intelligent resume screening, automated interview scheduling, and real-time candidate tracking",
        "founded": "2023",
        "team_size": "25-50",
        "headquarters": "San Francisco, CA",
        "website": "https://talentpipe.io",
        "features": ["AI Resume Screening", "Automated Interview Scheduling", "Pipeline Analytics", "Calendar Integration", "Skills-Based Matching"]
    }

@app.get("/api/metrics")
def get_metrics(db: Session = Depends(get_db)):
    total_candidates = db.query(Candidate).count()
    active_jobs = db.query(JobRequirement).filter(JobRequirement.is_active == True).count()
    scheduled_interviews = db.query(Interview).filter(Interview.status == "scheduled").count()
    applications_by_status = db.query(Application.status, db.func.count(Application.id)).group_by(Application.status).all()
    avg_match_score = db.query(db.func.avg(Resume.match_score)).scalar() or 0
    new_applications_this_week = db.query(Application).filter(Application.applied_at >= datetime.utcnow() - timedelta(days=7)).count()
    return {
        "total_candidates": total_candidates,
        "active_jobs": active_jobs,
        "scheduled_interviews": scheduled_interviews,
        "applications_by_status": dict(applications_by_status),
        "average_match_score": round(avg_match_score, 1),
        "new_applications_this_week": new_applications_this_week
    }

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total_applications = db.query(Application).count()
    hired = db.query(Application).filter(Application.status == ApplicationStatus.HIRED).count()
    rejected = db.query(Application).filter(Application.status == ApplicationStatus.REJECTED).count()
    in_pipeline = db.query(Application).filter(Application.status.in_([ApplicationStatus.NEW, ApplicationStatus.SCREENING, ApplicationStatus.INTERVIEW_SCHEDULED, ApplicationStatus.INTERVIEWED, ApplicationStatus.OFFERED])).count()
    conversion_rate = round((hired / total_applications * 100), 1) if total_applications > 0 else 0
    return {
        "total_applications": total_applications,
        "hired": hired,
        "rejected": rejected,
        "in_pipeline": in_pipeline,
        "conversion_rate": conversion_rate,
        "time_to_hire_days": 14
    }

@app.get("/api/recent-activity")
def get_recent_activity(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    recent_applications = db.query(Application).order_by(Application.applied_at.desc()).limit(limit).all()
    activity = []
    for app in recent_applications:
        candidate = db.query(Candidate).filter(Candidate.id == app.candidate_id).first()
        job = db.query(JobRequirement).filter(JobRequirement.id == app.job_requirement_id).first()
        if candidate and job:
            activity.append({
                "id": app.id,
                "candidate_name": candidate.name,
                "job_title": job.title,
                "status": app.status.value,
                "match_score": app.match_score,
                "timestamp": app.applied_at.isoformat()
            })
    return activity

@app.get("/api/chart-data")
def get_chart_data(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    labels = []
    applications_data = []
    interviews_data = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        labels.append(day.strftime("%a"))
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        apps_count = db.query(Application).filter(Application.applied_at >= day_start, Application.applied_at < day_end).count()
        interviews_count = db.query(Interview).filter(Interview.scheduled_at >= day_start, Interview.scheduled_at < day_end).count()
        applications_data.append(apps_count)
        interviews_data.append(interviews_count)
    return {"labels": labels, "applications": applications_data, "interviews": interviews_data}

@app.get("/api/pipeline")
def get_pipeline(db: Session = Depends(get_db)):
    pipeline_data = {}
    for status in ApplicationStatus:
        apps = db.query(Application).filter(Application.status == status).all()
        pipeline_data[status.value] = []
        for app in apps:
            candidate = db.query(Candidate).filter(Candidate.id == app.candidate_id).first()
            job = db.query(JobRequirement).filter(JobRequirement.id == app.job_requirement_id).first()
            if candidate and job:
                pipeline_data[status.value].append({
                    "id": app.id,
                    "candidate_name": candidate.name,
                    "candidate_email": candidate.email,
                    "job_title": job.title,
                    "match_score": app.match_score,
                    "applied_at": app.applied_at.isoformat() if app.applied_at else None
                })
    return pipeline_data

@app.get("/api/candidates")
def get_candidates(skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    candidates = db.query(Candidate).offset(skip).limit(limit).all()
    return [{
        "id": c.id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "current_company": c.current_company,
        "current_role": c.current_role,
        "years_experience": c.years_experience,
        "skills": c.skills.split(", ") if c.skills else [],
        "source": c.source,
        "created_at": c.created_at.isoformat() if c.created_at else None
    } for c in candidates]

@app.get("/api/candidates/{candidate_id}")
def get_candidate(candidate_id: str, db: Session = Depends(get_db)):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    applications = db.query(Application).filter(Application.candidate_id == candidate_id).all()
    interviews = db.query(Interview).filter(Interview.candidate_id == candidate_id).all()
    return {
        "id": candidate.id,
        "name": candidate.name,
        "email": candidate.email,
        "phone": candidate.phone,
        "current_company": candidate.current_company,
        "current_role": candidate.current_role,
        "years_experience": candidate.years_experience,
        "skills": candidate.skills.split(", ") if candidate.skills else [],
        "resume_text": candidate.resume_text,
        "source": candidate.source,
        "applications": [{"job_id": a.job_requirement_id, "status": a.status.value, "match_score": a.match_score} for a in applications],
        "interviews": [{"id": i.id, "scheduled_at": i.scheduled_at.isoformat() if i.scheduled_at else None, "status": i.status, "interview_type": i.interview_type} for i in interviews],
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None
    }

@app.post("/api/candidates")
def create_candidate(name: str, email: str, phone: Optional[str] = None, skills: Optional[str] = None, db: Session = Depends(get_db)):
    existing = db.query(Candidate).filter(Candidate.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Candidate with this email already exists")
    candidate = Candidate(id=str(uuid.uuid4()), name=name, email=email, phone=phone, skills=skills)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return {"id": candidate.id, "name": candidate.name, "email": candidate.email, "created_at": candidate.created_at.isoformat() if candidate.created_at else None}

@app.get("/api/jobs")
def get_jobs(active_only: bool = Query(True), db: Session = Depends(get_db)):
    query = db.query(JobRequirement)
    if active_only:
        query = query.filter(JobRequirement.is_active == True)
    jobs = query.all()
    return [{
        "id": j.id,
        "title": j.title,
        "department": j.department,
        "location": j.location,
        "employment_type": j.employment_type,
        "min_experience": j.min_experience,
        "required_skills": j.required_skills.split(", ") if j.required_skills else [],
        "salary_range": f"${j.salary_range_min:,.0f} - ${j.salary_range_max:,.0f}" if j.salary_range_min else None,
        "description": j.description,
        "is_active": j.is_active,
        "application_count": db.query(Application).filter(Application.job_requirement_id == j.id).count(),
        "created_at": j.created_at.isoformat() if j.created_at else None
    } for j in jobs]

@app.post("/api/jobs")
def create_job(title: str, department: str, location: str, description: str, required_skills: str, min_experience: float = 0, salary_range_min: Optional[float] = None, salary_range_max: Optional[float] = None, db: Session = Depends(get_db)):
    job = JobRequirement(id=str(uuid.uuid4()), title=title, department=department, location=location, description=description, required_skills=required_skills, min_experience=min_experience, salary_range_min=salary_range_min, salary_range_max=salary_range_max)
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"id": job.id, "title": job.title, "department": job.department, "created_at": job.created_at.isoformat() if job.created_at else None}

@app.get("/api/interviews")
def get_interviews(upcoming: bool = Query(True), db: Session = Depends(get_db)):
    query = db.query(Interview)
    if upcoming:
        query = query.filter(Interview.scheduled_at >= datetime.utcnow(), Interview.status == "scheduled")
    interviews = query.order_by(Interview.scheduled_at.asc()).all()
    return [{
        "id": i.id,
        "candidate_name": db.query(Candidate).filter(Candidate.id == i.candidate_id).first().name if db.query(Candidate).filter(Candidate.id == i.candidate_id).first() else "Unknown",
        "job_title": db.query(JobRequirement).filter(JobRequirement.id == i.job_requirement_id).first().title if db.query(JobRequirement).filter(JobRequirement.id == i.job_requirement_id).first() else "Unknown",
        "interviewer": db.query(User).filter(User.id == i.interviewer_id).first().name if db.query(User).filter(User.id == i.interviewer_id).first() else "Unknown",
        "scheduled_at": i.scheduled_at.isoformat() if i.scheduled_at else None,
        "duration_minutes": i.duration_minutes,
        "interview_type": i.interview_type,
        "status": i.status,
        "notes": i.notes
    } for i in interviews]

@app.post("/api/interviews")
def schedule_interview(candidate_id: str, job_requirement_id: str, interviewer_id: str, scheduled_at: datetime, interview_type: str = "technical", duration_minutes: int = 60, db: Session = Depends(get_db)):
    if not db.query(Candidate).filter(Candidate.id == candidate_id).first():
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not db.query(JobRequirement).filter(JobRequirement.id == job_requirement_id).first():
        raise HTTPException(status_code=404, detail="Job requirement not found")
    if not db.query(User).filter(User.id == interviewer_id).first():
        raise HTTPException(status_code=404, detail="Interviewer not found")
    interview = Interview(id=str(uuid.uuid4()), candidate_id=candidate_id, job_requirement_id=job_requirement_id, interviewer_id=interviewer_id, scheduled_at=scheduled_at, interview_type=interview_type, duration_minutes=duration_minutes)
    db.add(interview)
    application = db.query(Application).filter(Application.candidate_id == candidate_id, Application.job_requirement_id == job_requirement_id).first()
    if application:
        application.status = ApplicationStatus.INTERVIEW_SCHEDULED
    db.commit()
    db.refresh(interview)
    return {"id": interview.id, "scheduled_at": interview.scheduled_at.isoformat() if interview.scheduled_at else None, "status": "scheduled"}

@app.get("/api/applications")
def get_applications(status: Optional[ApplicationStatus] = None, db: Session = Depends(get_db)):
    query = db.query(Application)
    if status:
        query = query.filter(Application.status == status)
    applications = query.order_by(Application.applied_at.desc()).all()
    return [{
        "id": a.id,
        "candidate_name": db.query(Candidate).filter(Candidate.id == a.candidate_id).first().name if db.query(Candidate).filter(Candidate.id == a.candidate_id).first() else "Unknown",
        "job_title": db.query(JobRequirement).filter(JobRequirement.id == a.job_requirement_id).first().title if db.query(JobRequirement).filter(JobRequirement.id == a.job_requirement_id).first() else "Unknown",
        "status": a.status.value,
        "match_score": a.match_score,
        "applied_at": a.applied_at.isoformat() if a.applied_at else None
    } for a in applications]

@app.post("/api/applications")
def create_application(candidate_id: str, job_requirement_id: str, db: Session = Depends(get_db)):
    if not db.query(Candidate).filter(Candidate.id == candidate_id).first():
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not db.query(JobRequirement).filter(JobRequirement.id == job_requirement_id).first():
        raise HTTPException(status_code=404, detail="Job requirement not found")
    existing = db.query(Application).filter(Application.candidate_id == candidate_id, Application.job_requirement_id == job_requirement_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Application already exists")
    application = Application(id=str(uuid.uuid4()), candidate_id=candidate_id, job_requirement_id=job_requirement_id)
    db.add(application)
    db.commit()
    db.refresh(application)
    return {"id": application.id, "status": application.status.value, "applied_at": application.applied_at.isoformat() if application.applied_at else None}

@app.get("/api/resumes")
def get_resumes(min_score: Optional[float] = Query(None, ge=0, le=100), db: Session = Depends(get_db)):
    query = db.query(Resume)
    if min_score is not None:
        query = query.filter(Resume.match_score >= min_score)
    resumes = query.order_by(Resume.match_score.desc()).all()
    return [{
        "id": r.id,
        "candidate_name": db.query(Candidate).filter(Candidate.id == r.candidate_id).first().name if db.query(Candidate).filter(Candidate.id == r.candidate_id).first() else "Unknown",
        "job_title": db.query(JobRequirement).filter(JobRequirement.id == r.job_requirement_id).first().title if db.query(JobRequirement).filter(JobRequirement.id == r.job_requirement_id).first() else "Unknown",
        "match_score": r.match_score,
        "parsed_skills": r.parsed_skills.split(", ") if r.parsed_skills else [],
        "is_shortlisted": r.is_shortlisted,
        "created_at": r.created_at.isoformat() if r.created_at else None
    } for r in resumes]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)