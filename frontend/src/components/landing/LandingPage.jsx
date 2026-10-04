import Navbar from './Navbar'
import Hero from './Hero'
import RepositoryAnalyzer from './RepositoryAnalyzer'
import ProblemSection from './ProblemSection'
import WorkflowSection from './WorkflowSection'

import SupportedLanguages from './SupportedLanguages'
import SecuritySection from './SecuritySection'
import FeaturesSection from './FeaturesSection'
import AgentsSection from './AgentsSection'
import MultiRepoSection from './MultiRepoSection'
import ArchitectureSection from './ArchitectureSection'
import GithubIntegration from './GithubIntegration'
import FinalCTA from './FinalCTA'
import Footer from './Footer'

export default function LandingPage({ 
  repoUrlInput, 
  setRepoUrlInput, 
  startAnalysis, 
  isSubmitting 
}) {
  return (
    <div className="min-h-screen bg-[#050505] text-[#FAFAFA] selection:bg-[#8B5CF6]/30">
      <Navbar />
      <main className="flex flex-col items-center w-full overflow-hidden">
        <Hero />
        <RepositoryAnalyzer 
          repoUrlInput={repoUrlInput} 
          setRepoUrlInput={setRepoUrlInput} 
          startAnalysis={startAnalysis} 
          isSubmitting={isSubmitting} 
        />
        <ProblemSection />
        <WorkflowSection />

        <SupportedLanguages />
        <SecuritySection />
        <FeaturesSection />
        <AgentsSection />
        <MultiRepoSection />
        <ArchitectureSection />
        <GithubIntegration />
        <FinalCTA 
          startAnalysis={() => document.getElementById('repo-analyzer')?.scrollIntoView({ behavior: 'smooth' })} 
        />
      </main>
      <Footer />
    </div>
  )
}
